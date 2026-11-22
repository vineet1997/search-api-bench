# search-api-bench

**Route per call, not per vendor.**

An empirical comparison of two web search/fetch APIs — [Exa](https://exa.ai) (paid) and
[TinyFish](https://www.tinyfish.ai) (free) — across the four kinds of call a real research
pipeline actually makes. 462 records from 657 provider API calls, 3 repeats, one date:
**2026-08-28**.

The useful output is not a winner. It is a routing table, and a harness you can point at
any two providers.

```
S1  look up a named thing      TinyFish   101.7% of Exa   -> REPLACE
S2  discover from a description Exa        TinyFish 78.4%  -> PARTIAL
S3  expand a seed URL           Exa        TinyFish  0.4%  -> KEEP EXA
S4  fetch a URL's text          TinyFish   103.0% of Exa   -> REPLACE

weighted total: TinyFish 88.8% of Exa   <- a number you should throw away
```

The 88.8% is the least interesting line here. It averages four jobs that the two products
win differently, which is exactly the mistake the rest of this repo exists to avoid.

---

## The short version

**TinyFish for lookup and fetch. Exa for discovery and expansion.**

| Job | Use | Why |
|---|---|---|
| Look up a **named** thing | **TinyFish** | Ties Exa on recall (98.0%), ranks better (MRR 0.943 vs 0.869), costs $0 |
| **Discover** from a description | **Exa `type=neural`** | 50.0% hit@10 vs 41.7%. TinyFish has no semantic mode at all |
| **Expand** a seed URL into new domains | **Exa `findSimilar`** | 8.2 new domains/seed vs 0.3. No TinyFish equivalent exists |
| **Fetch** a URL's text | **TinyFish** | Ties on success, better anchor recall (55.7% vs 51.4%), $0. Note the 1,000 URLs/day cap |

Full per-call rules, including the ones that are not about vendors at all:
[`SEARCH-ROUTING.md`](SEARCH-ROUTING.md).

---

## Three findings that outlived the scoreboard

### 1. My own bug reversed my own headline

The first run said TinyFish won semantic discovery at **105.5% of Exa** — the answer I
wanted, since I was trying to stop paying for Exa.

My host matcher required an exact match. So when Exa returned
`alignment.anthropic.com` — the actual Anthropic Fellows page — it scored as a *miss*
against gold `anthropic.com`. Accepting subdomains moved S2 from **TinyFish 105.5%** to
**Exa 78.4%**. The bug had been hiding a real advantage for the product I was hoping to
drop.

Two other metrics changed after I saw data: a suite where both contestants scored 0.0%
(I was measuring a capability neither product claims), and an extraction metric that
turned out to be grading PDF typography rather than content. All three are written up in
[`RUBRIC.md` §9](RUBRIC.md), including the one that cost me my preferred answer.

Post-hoc metric changes are how a benchmark gets quietly rigged. They are listed so you
can judge them yourself rather than take my word for it.

### 2. A failed fetch is loud. Mislabelled content is silent.

On 2026-08-28, I asked Exa's `/contents` for the RAG paper, `arxiv.org/abs/2005.11401`.

What came back was **the correct paper body with another paper's title and publication
date attached to it**:

```
# Affordance-Compiled Intelligence: Observable-Only Cognitive Impedance
  Matching for No-Meta LLM-Integrated Systems
arXiv (Cornell University). Published: 2026-03-13. Preprint. 3,030 citations.
```

Underneath that header sat the real RAG paper — 74.3% of its distinctive sentences,
verbatim, with the correct title and author line in the body. The header's title belongs to
a genuine 2026 preprint by K. Takahashi, which is published on **Zenodo, not arXiv**. The
date is six years off. The response was **byte-identical for the `/abs/` and `/pdf/`
forms**, across all 3 repeats — six identical responses from two different URLs. TinyFish
and Firecrawl independently returned correctly-labelled text for both.

This is worse than a wrong document, because a wrong document fails a content check. Here
the content is right, so the content check passes, and an agent asking "what is this paper
and when was it published?" gets `2026-03-13` for a paper from May 2020. **A failed fetch is
visible; wrong content arrives looking exactly like right content and gets ingested as
fact.**

**Scope, stated plainly:** one URL pair out of 24, on one date, in one run. 1 collision
group for Exa, 0 for TinyFish. I am not claiming Exa is broadly unreliable — it won two of
my four suites and I still pay for it. I am claiming this failure mode exists, that it is
invisible without a second opinion, and that I had never once tested for it.

### This has since been fixed

**I re-ran the same check on 2026-11-22. It no longer reproduces.** Exa now returns the
correct title and the correct identifier line (`arXiv:2005.11401v4 [cs.CL] 12 Apr 2021`),
and the entire metadata-enrichment block the bad header lived in — title, publication date,
"Preprint", citation count, per-author h-index figures, topic list — is gone from the
response. What comes back is plain extracted paper text.

I did not report it between those two dates, so I can't claim any credit for the fix. All I
can say is that the behaviour was there on 2026-08-28, that it is not there on 2026-11-22,
and that the layer it lived in was removed at some point in between.

*One thing that did not change: Exa still returns byte-identical text for the `/abs/` and
`/pdf/` forms (it serves the paper for both). TinyFish still distinguishes them — 4,846
chars for the abstract page, 69,080 for the PDF. That is a defensible design choice rather
than a bug, but it is also why Exa's 20% anchor recall on arXiv abstract pages would
probably still reproduce: the ground truth for that URL is the abstract page, not the
paper.*

The reason this stays in the README now that it's fixed is the rule it produced, which
hasn't changed: **if an extraction feeds a citation, a dataset, or a claim you will publish,
fetch it twice with different providers and compare.** That is cheap when one of the two is
free. A fetch that fails is loud enough to catch. This one wasn't, and it took a scorer
disagreeing with itself to surface it.

### 3. The search is 15% of the bill

Exa list price, August 2026, `type=auto`: $7/1k searches (≤10 results), +$1/1k per extra
result, +$1/1k pages of text. On a 25-result sweep with text:

| Component | per 1k calls | Share |
|---|---|---|
| Base search (first 10 results) | $7 | 15% |
| 15 additional results (11–25) | $15 | 32% |
| Text for all 25 pages | $25 | 53% |
| **Total** | **$47** | |

`numResults` and `text` are **85% of the bill**. Going from 25 results with text to 10
without takes $47 → $7. Before comparing vendors at all, the biggest cost lever in my own
code was a parameter I had never tuned.

*Caveat: Exa now also lists `lite` and `instant` at $4/1k. This benchmark used `auto`,
because that is what my code shipped — so the measured cost gap is against Exa's $7 tier,
not its cheapest. `findSimilar` is no longer priced on the public pricing page; the $17
figure in the routing guide is derived from the Aug 2026 list price.*

---

## Results

Four suites, weighted by how often my own pipeline makes each kind of call — not by how
interesting the call is. Weights are declared in `score.py:WEIGHTS`; change them if you
disagree and re-score in a second.

| Suite | Metric | Exa | TinyFish | Verdict |
|---|---|---|---|---|
| **S1** known-item (25 q, w 0.25) | recall@20 | 98.0% | **98.0%** | **TinyFish** (101.7%) |
| | nDCG@20 / MRR | 85.1% / 0.869 | **90.3% / 0.943** | ranks better |
| | latency p50 | **1,282 ms** | 3,645 ms | Exa 2.8× faster, 1 call vs 2 |
| **S2** discovery (12 q, w 0.30) | hit@10 | **50.0%** | 41.7% | **Exa** (78.4%) |
| | recall@20 | **16.7%** | 11.1% | absolutes are a floor — see limits |
| **S3** expansion (10 seeds, w 0.15) | new domains/seed | **8.2** | 0.3 | **Exa** (0.4%) |
| | off-domain rate | **50.1%** | 6.0% | |
| **S4** extraction (24 URLs, w 0.30) | success | 91.7% | 91.7% | **TinyFish** (103.0%) |
| | anchor recall | 51.4% | **55.7%** | |
| | latency p50 | **557 ms** | 1,365 ms | Exa 2.4× faster |

### That 91.7% tie is a ceiling, not a shortfall

Both providers failed on **exactly the same two URLs** — `ias.edu/scholars/apply` and
`turing.ac.uk/work-turing/studentships-and-fellowships` — in all three repeats. Both of
those also defeated the Firecrawl referee (195 and 189 chars of nothing).

So both providers fetched **everything that was fetchable at all**. 22 of 24 is the ceiling
for this URL set, and they both hit it. That is a result about the web, not about the
vendors.

### Extraction by page type (anchor recall)

| Page type | Exa | TinyFish |
|---|---|---|
| arXiv abstract | 20% | **100%** |
| PDF | 60% | **80%** |
| JS SPA | **86.7%** | 66.7% |
| marketing page | 80% | 80% |
| long static | 60% | 60% |
| docs SPA | 40% | 40% |
| EU gov SPA | 40% | 40% |
| **EU cookie wall** | 26.7% | 26.7% |
| **soft paywall** | 0% | 20% |

**Both providers fail cookie walls and paywalls.** Neither is a scraping solution for
consent-gated EU sites — budget for a real browser there.

*The arXiv-abstract row (20% vs 100%) is a symptom of finding #2, not an independent
result: Exa served ~70k chars of full-paper body for an `/abs/` URL whose ground truth was
the 9.3k-char abstract page.*

### One clean negative result

TinyFish's `purpose` parameter returned **identical URL lists in 36 of 36** comparisons. It
is intent context, not a semantic-search knob. Stop passing it and expecting better
ranking.

---

## What this does **not** show

Read this section before quoting any number above.

- **It is not a general search-quality benchmark.** The weights are my pipeline's call mix.
  The corpus is institutional program pages — fellowships, residencies, visiting-researcher
  posts. Your weights are different, and the per-suite ratios matter more than the total.
- **S2's absolute recall (16.7% / 11.1%) is a floor, not an estimate.** My gold sets are too
  narrow. Exa returned `cbai.ai`, `iliad.ac` and `globalaisafetyfellowship.com` — real
  fellowships that should plausibly have been gold and weren't. Both engines faced the
  identical set, so the **ratio** holds; the absolutes understate both. Widening these is
  the highest-value open fix and the thing I'd most want other eyes on.
- **Gold sets are hand-curated by one person.** Me. Mitigated by host-level matching,
  non-exhaustive recall scoring and a `verify-gold` command. Not eliminated.
- **S3's TinyFish surrogate is one design.** A better workaround may exist; 0.4% is a floor
  on the workaround, not a measurement of TinyFish.
- **S2 compares a semantic engine to a keyword engine.** Deliberately. It measures the
  outcome ("can it find these programs"), not the mechanism. Do not read it as "TinyFish
  ranks badly."
- **Latency was measured from India on a single residential connection.** Directional only.
  It contributes **0** to every verdict.
- **The numbers are from one date.** Live indexes drift. Re-run both providers together;
  never compare across dates. I would not trust these past ~6 months without a re-run.
- **One run, one author, no second reviewer.** Three repeats protect against flaky
  responses, not against my own judgement.
- **The arXiv finding is one reproducible observation on 24 URLs from one date**, and it has
  since been fixed (re-checked 2026-11-22). It was never a measured error rate, and it is
  not a current defect.
- **Exa was tested on `type=auto` ($7/1k), not its cheaper `lite`/`instant` tiers ($4/1k).**
  The cost comparison reflects that.

---

## On "free"

TinyFish Search and Fetch are **$0.00 per request**, at any wallet balance, no card. As of
2026-11-17 that still holds. But the limits have tightened since this benchmark ran:

| | At run time (2026-08-28) | Now (2026-11-17) |
|---|---|---|
| Search | 30 req/min | 30 req/min **+ 500 req/hour** |
| Fetch | 150 urls/min | 150 urls/min **+ 1,000 urls/day** |

**An earlier version of this repo called TinyFish "uncapped in total volume." That is no
longer true.** There is now a hard ceiling of 1,000 fetched URLs per day. "Use TinyFish for
fetch" is sound at research volume and **breaks above 1,000 URLs/day** — a normal day for
anything crawling seriously. Check the current limits yourself before migrating; this is
the kind of thing that changes.

The run itself made 72 fetches, far inside even the new limits, so the measurements are
unaffected.

**And: free is a pricing decision, not a contract.** Per-call routing keeps Exa integrated
for the two calls that have no substitute, which is also the cheap insurance if the free
tier ends.

---

## How it stays honest

The parts worth stealing, whatever you're comparing:

1. **Collection and judgement are separate programs.** `run_bench.py` only writes raw
   JSONL. `score.py` makes **zero network calls and zero model judgements**. Same raw files
   + same fixtures ⇒ byte-identical scorecard. *(Verified: three consecutive `--json` runs
   hash identical.)* This is what let me rewrite the rubric three times on data I had
   already paid for — and it is the only reason finding #1 was fixable instead of
   expensive.
2. **The decision rule was declared before the run.** ≥0.90 of Exa = REPLACE, 0.60–0.90 =
   PARTIAL, <0.60 = KEEP. Written down in `RUBRIC.md` §6 before any call went out, so the
   result could not be rationalised into a verdict afterwards.
3. **Ground truth comes from a third party.** S4 anchors are derived from **Firecrawl**, a
   provider that is not competing. Neither contestant gets to define what correct
   extraction means. The moment you ask one contestant for the right answer, you've lost.
4. **Frozen, committed fixtures.** Queries and gold sets are files, not runtime generation.
   Editing one is a visible diff.
5. **Each provider is scored on its best variant** — the most generous available reading for
   the challenger. If it loses, it loses on merit.
6. **Repeats are averaged, not cherry-picked.** `--repeat 3`.
7. **Raw data is published.** All 462 records are in `raw/`. Every number above re-derives
   from them with `score.py`. A benchmark whose raw data isn't published is an assertion.
8. **Distrust unanimous results.** Both places the two products scored *identically* — the
   0.0% in S3, the exact-tie anchor rows — turned out to be broken measurement, not real
   ties. Agreement between competitors is a smell.

---

## Reproducing

```bash
pip install requests tinyfish==0.6.1
cp .env.example .env.local      # add your own EXA_API_KEY, TINYFISH_API_KEY, FIRECRAWL_API_KEY
```

Re-score the published run — **free, no network, no keys needed**:

```bash
python score.py 20260828-124047
```

```bash
python score.py 20260828-124047 --json
```

Run it yourself. Check the budget first — `--dry-run` spends nothing:

```bash
python run_bench.py all --dry-run
```

```bash
python run_bench.py verify-gold
```

```bash
python run_bench.py build-anchors
```

```bash
python run_bench.py all --repeat 3
```

`verify-gold` confirms every gold host still resolves, using the free TinyFish fetch, so it
costs nothing — fix any DEAD hosts before trusting a run. `build-anchors` rebuilds S4
ground truth from Firecrawl. The real run at `--repeat 3` cost **213 Exa calls** and 444
TinyFish calls; price that against your own plan before starting.

---

## Layout

```
README.md              you are here
RUBRIC.md              methodology, threats to validity, and the changelog (§9)
SEARCH-ROUTING.md      the per-call routing guide this produced
run_bench.py           collection only. writes raw JSONL, judges nothing
score.py               judgement only. zero network calls, zero model judgement
providers.py           provider adapters, normalised to one response shape
fixtures/              frozen queries and gold sets (4 files)
raw/                   all 462 raw records from run 20260828-124047
```

---

## Adding a provider

`providers.py` normalises every adapter to one shape, so the scorer never knows which
product produced a row:

```
search -> {"ok", "latency_ms", "calls", "urls", "rows", "error"}
fetch  -> {"ok", "latency_ms", "calls", "text", "error"}
```

Write an adapter that returns that, add it to the suite you care about, and the existing
metrics apply unchanged. Brave, Serper, Tavily, Jina and Firecrawl would all fit; Firecrawl
is already wired in as the referee.

---

## Licence

MIT. The fixtures and raw data are published under the same terms — fork them, widen the
gold sets, tell me where I was wrong.
