# Exa vs TinyFish — evaluation rubric

**Question being answered:** can TinyFish replace Exa in this repo's stack, and if only
partly, on exactly which calls?

**Status: run 2026-08-28** (`run_id 20260828-124047`, 3 repeats, 462 records from 657
provider API calls, 18 not-ok records).
Results and the resulting routing rules live in [`SEARCH-ROUTING.md`](SEARCH-ROUTING.md).
**Read §9 (changelog) before quoting any number** — three metric changes were made after
seeing raw data, and one of them reversed the S2 verdict.

---

## 1. What we actually use Exa for

This is not a generic search bake-off. The calling project — a research pipeline that hunts
down institutional programme pages — makes exactly four kinds of Exa call, and the rubric
weights them by how much work they do there:

| # | Call | What it does for the pipeline | Weight |
|---|------|------------------------------|--------|
| 1 | `search` type=auto | keyword sweeps for named programmes | **0.25** |
| 2 | `search` type=neural | precedent mining from a descriptive sentence — the call the pipeline's own comments describe as "best for precedent mining" | **0.30** |
| 3 | `findSimilar` | lookalike expansion; described in the pipeline as "the cheapest way to grow a seed list" | **0.15** |
| 4 | `contents` | URL → page text for verification | **0.30** |

**These weights are the pipeline's call mix, not a claim about general importance.** If your
mix differs, change them and re-score — which is the point of the per-suite ratios below.

Weights sum to 1.0 and are declared in `score.py:WEIGHTS`. Change them there if you
disagree — the scorer re-runs offline in a second.

---

## 2. Capability matrix (established before any test ran)

Read from TinyFish's docs and confirmed against the installed SDK (`tinyfish==0.6.1`):

| Exa capability we use | TinyFish equivalent | Verdict |
|---|---|---|
| keyword/auto search | `search.query()` | present |
| domain include/exclude | `include_domains` / `exclude_domains` | present *(SDK only — undocumented on the docs page)* |
| date filtering | `after_date`/`before_date`/`recency_minutes` | present, richer than Exa |
| scholarly metadata | `domain_type="research_paper"` → authors, venue, year, `cited_by_count`, `pdf_url` | **better than Exa** |
| **neural / semantic search** | **none** — `purpose` is intent *context*, not embedding retrieval | **absent** |
| **findSimilar** | **none** | **absent** |
| inline result text | snippet only (~150 chars) vs Exa's 2 000 | degraded |
| results per call | fixed 10/page | Exa takes `numResults` up to 25+ |
| URL → text | `fetch.get_contents()`, batch ≤10, JS render, PDF, CSS selectors, caching | **better than Exa** |

Two hard gaps (neural, findSimilar) sit on 0.45 of the weight. The benchmark exists to
measure how much that actually costs in outcomes, not to re-confirm they're missing.

---

## 3. Suites

Each suite writes raw JSONL; nothing is judged at collection time.

### S1 — Known-item retrieval (w 0.25)
25 queries naming a real program; exactly one host is correct.
Fixture: `fixtures/known_item.json`. Exa `type=auto` vs TinyFish web.
*Answers: for plain keyword sweeps, is TinyFish's index as good?*

### S2 — Semantic discovery (w 0.30)
12 **descriptive-sentence** queries ("a paid six-month research residency for an
experienced engineer without a PhD"). Gold is a non-exhaustive set of qualifying hosts,
scored by Recall@20 — extra good results are never penalised.
Exa `type=neural` vs TinyFish plain **and** TinyFish with `purpose` set.
*Answers: how much does having no neural mode actually cost?* This is the decisive suite.

### S3 — Lookalike expansion (w 0.15)
10 seed program URLs → sibling programs. Exa `findSimilar` vs a TinyFish **surrogate**
(fetch the seed's outbound links + one search built from the seed's own title).
*Answers: can the missing endpoint be worked around, and at what call cost?*

### S4 — Content extraction (w 0.30)
24 URLs across 15 categories: PDF, JS SPA, EU cookie wall, legacy gov, soft paywall,
JSON endpoint, long static. Exa `contents` vs TinyFish `fetch`.
*Answers: can TinyFish replace `exa_contents`?*

---

## 4. How this stays deterministic

Determinism is the whole point, so it's enforced structurally, not by discipline:

1. **Collection and judgement are separate processes.** `run_bench.py` only writes raw
   JSONL. `score.py` makes zero network calls and contains zero model judgement. Same
   raw files + same fixtures ⇒ byte-identical scorecard, always. *(Verified: three
   consecutive `--json` runs diffed identical.)*
2. **Frozen fixtures.** Queries and gold sets are committed files, not generated at
   runtime. Editing them is a visible diff.
3. **Host-level URL matching** after canonicalisation (strip scheme/`www`/query/
   fragment/trailing slash). A program moving `/apply` → `/applications` does not
   silently change a score.
4. **Ground truth for S4 comes from a third party.** Anchors are derived from
   **Firecrawl** (`build-anchors`), a third provider that is not competing. Neither contestant gets to
   define what correct extraction means. A provider scores on how many referee
   sentences it reproduces.
5. **Repeats are averaged, not cherry-picked** (`--repeat 3`), so one flaky response
   can't swing a verdict.
6. **Each provider is scored on its best variant** — the most generous possible reading
   for TinyFish. If it loses, it loses on merit.

**Not deterministic, and labelled as such:** latency (p50/p95) and live index drift.
Latency is reported but contributes 0 to the verdict.

---

## 5. Metrics

| Metric | Meaning |
|---|---|
| `hit@10` | fraction of queries with ≥1 gold host in top 10 |
| `recall@k` | share of gold hosts found in top k (k=20) |
| `nDCG@k` | rank-weighted recall, binary relevance |
| `MRR` | 1/rank of first gold hit |
| `avg_calls` | API calls to reach 20 results — TinyFish needs 2 pages where Exa needs 1 |
| `success` | non-empty, non-error responses |
| `anchor_recall` | share of referee sentences reproduced (S4) |
| `coverage_vs_referee` | chars returned ÷ referee chars, capped at 1.0 (S4) |
| `boilerplate_hits` | cookie/JS-wall junk markers in first 4 000 chars — **lower is better** (S4) |

**Headline score per suite** (the one number feeding the verdict):

- S1–S3: `0.5·recall@k + 0.3·nDCG@k + 0.2·hit@10`
- S4: `0.5·success + 0.5·anchor_recall`

---

## 6. Decision rule

Deterministic, declared before the run so results can't be rationalised after the fact.

For each suite: `ratio = headline(tinyfish) / headline(exa)`

| ratio | verdict |
|---|---|
| ≥ **0.90** | **REPLACE** — TinyFish takes this call |
| 0.60 – 0.90 | **PARTIAL** — usable as fallback / bulk tier, Exa stays primary |
| < 0.60 | **KEEP EXA** |

A surface whose capability is **absent** cannot score REPLACE regardless of surrogate
performance — a workaround is not a replacement.

**Overall recommendation** is per-surface, not global. The realistic outcomes:

- *Full replace* — TinyFish ≥0.90 on all four. Unlikely: S2 and S3 have no mechanism.
- *Partial replace (expected)* — TinyFish takes S1 + S4 (0.55 of weight, and S4 looks
  like a genuine upgrade); Exa is kept purely for `neural` + `findSimilar`.
- *Keep Exa* — TinyFish fails S1 or S4 too.

Cost note: Exa is only charged for calls it still serves. If the expected outcome lands,
Exa spend drops by roughly the S1+S4 share of call volume while keeping the two
capabilities that have no substitute — which is a better result than a clean swap.

---

## 7. Threats to validity

Stated up front so the run isn't over-read:

- **Gold sets are hand-curated by one author.** Mitigated by host-level matching,
  non-exhaustive recall scoring, and `verify-gold`. Not eliminated — a second pair of
  eyes on `fixtures/*.json` is worth more than another metric.
- **S2 compares a semantic engine to a keyword engine.** Deliberate. It measures
  outcome ("can it find these programs"), not mechanism. Don't read it as "TinyFish's
  ranking is bad."
- **S3's surrogate is one design.** A better workaround may exist; the number is a floor.
- **Live indexes drift.** Re-run both providers together, never compare across dates.
- **Free ≠ unlimited.** 30 search/min and 150 fetch-urls/min are hard ceilings. The
  runner paces at 2 s between searches. A burst-heavy sweep will hit 429s that this
  benchmark's pacing hides — test burst behaviour separately before migrating.
- **Single-vendor risk.** A free tier is a pricing decision, not a contract.

---

## 8. How to run

```bash
python bench/run_bench.py verify-gold
```

Confirms every gold host still resolves (uses free TinyFish fetch, costs nothing).
**Fix any DEAD hosts before continuing** — a stale fixture silently deflates both scores.

```bash
python bench/run_bench.py build-anchors
```

Builds S4 ground truth from Firecrawl. Run once; commit the updated `fixtures/fetch.json`.

```bash
python bench/run_bench.py all --dry-run
```

Prints the call budget (currently **71 Exa calls / 152 TinyFish calls**) without spending anything.

```bash
python bench/run_bench.py all --repeat 3
```

The real run. Then:

```bash
python bench/score.py <run_id>
```

Add `--json` for a machine-readable scorecard. Re-score as often as you like — it never
re-spends an API call.

---

## 9. Changelog — methodology changed after the first run

Three changes were made *after* seeing raw data. All are recorded here because
post-hoc metric changes are exactly how a benchmark gets rigged, and the reader
should be able to judge them.

**(a) Subdomain matching — bug fix.** Original `hits()` required an exact host
match, so Exa finding `alignment.anthropic.com` (the real Anthropic Fellows page)
scored as a miss against gold `anthropic.com`. Now a result matches if it is the
gold host *or a subdomain of it*. **This moved S2 from TinyFish 105.5% to
TinyFish 78.4%** — it had been hiding a genuine Exa advantage. Applied
identically to both providers.

**(b) S3 metric redefined.** The original metric assumed `findSimilar` returns
sibling *organisations*. The raw data refuted that: 46% of Exa's results and 91%
of the TinyFish surrogate's were on the seed's own domain, and gold-hit rate was
0.0% for **both**. The suite was testing a capability neither product claims.
It now measures the job the pipeline actually uses it for — **new-domain
yield** when growing a seed list. The old gold-hit rate is still reported as a
secondary column.

**(c) Anchor matching normalised.** Exact substring matching on PDFs was
measuring glyph rendering, not content: the referee emits
`Patrick Lewis††, Ethan Perez*` where another extractor emits
`Patrick Lewis†‡, Ethan Perez⋆`. Anchors are now compared after lowercasing and
stripping non-alphanumerics. This *raised both* providers (Exa 38.6→51.4%,
TinyFish 44.3→55.7%) and did not change the S4 verdict.

The 18 not-ok records: 12 in S4 (6 Exa `empty_text`, 6 TinyFish `bot_blocked`, all on
`ias.edu` and `turing.ac.uk`) and 6 in S3 (the TinyFish surrogate on those same two hosts).
Both providers failed on exactly the same two URLs, and both of those also defeated the
Firecrawl referee — so 22/24 is the ceiling for this URL set, not a shortfall.

Also: S4's `anchor_recall` and `coverage` are computed over the **14 of 24 URLs
where the Firecrawl referee produced usable ground truth**. Firecrawl was itself
blocked on `ias.edu`, `santafe.edu` and `turing.ac.uk` (96–195 chars). `success`
is still computed over all 24 — a provider beating the referee is a real result.

### Known weakness in the current numbers

**S2's absolute recall is low for both providers (16.7% / 11.1%) because the gold
sets are too narrow, not because the engines failed.** Exa returned `cbai.ai`,
`iliad.ac` and `globalaisafetyfellowship.com` — real AI-safety fellowships that
should plausibly be gold but aren't. Both engines face the identical gold set, so
the *ratio* is meaningful; the *absolute* numbers are a floor, not an estimate of
real-world recall. Widening S2's gold sets is the highest-value next fix.
