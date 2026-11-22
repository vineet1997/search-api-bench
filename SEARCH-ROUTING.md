# Web search & fetch — routing rules

**For agents (Claude / ChatGPT / Cursor) and humans. Portable: drop this file into any
project, or reference it from `CLAUDE.md`.**

Two providers, four jobs. They are not substitutes — each wins different calls. Route by
*job*, not by preference.

Measured 2026-08-28 against `exa` and `tinyfish==0.6.1`: 462 records from 657 provider
API calls, 3 repeats. Pricing and rate limits re-checked 2026-11-17; the arXiv finding below
re-checked 2026-11-22.
Method and raw data: [`bench/RUBRIC.md`](bench/RUBRIC.md). Re-run before trusting these
numbers past ~6 months.

---

## TL;DR routing table

| Job | Use | Why |
|---|---|---|
| Look up a **named** thing ("Recurse Center application") | **TinyFish** | Ties Exa on recall (98%), ranks better (MRR 0.94 vs 0.87), costs $0 |
| **Discover** from a description ("a 6-month residency for an engineer without a PhD") | **Exa `type=neural`** | Exa 50% hit@10 vs 42%; TinyFish has no semantic mode at all |
| **Expand** a seed URL into new domains | **Exa `findSimilar`** | 8.2 new domains/seed vs 0.3. No TinyFish equivalent exists |
| **Fetch** a URL's text | **TinyFish** | Ties on success (91.7%), better anchors (55.7% vs 51.4%), $0 — but note the 1,000 URLs/day cap |
| Scholarly search (papers, citations) | **TinyFish** `domain_type="research_paper"` | Returns authors, venue, year, `cited_by_count`, `pdf_url`. Exa has no equivalent |
| Bulk / high-volume anything | **TinyFish first, Exa on miss** | Free. Escalate only when TinyFish returns nothing |

**One-line version:** *TinyFish for lookup and fetch, Exa for discovery and expansion.*

---

## Rules for agents

1. **Default to TinyFish for `search` and `fetch`.** It is free and at least as good on
   those two jobs. Do not spend Exa credits on a query that names its target.
2. **Escalate to Exa `type=neural` when the query is a description, not a name.** If the
   query has no proper noun in it, TinyFish is the wrong tool.
3. **Never try to emulate `findSimilar`.** Scraping a page's outbound links returns the
   page's own subpages (91% same-domain, measured). If you need lookalike expansion,
   call Exa or don't do it.
4. **Ask for 10 results, not 25, unless you need more.** On Exa, results 11–25 plus their
   text are 85% of the bill (see cost table).
5. **Normalise URLs to the `www.` form before fetching.** *Both* providers return nothing
   for `https://jsps.go.jp/` and full text for `https://www.jsps.go.jp/`. Neither follows
   the apex→www redirect. This is the single most common silent failure.
6. **Don't pass `purpose` to TinyFish expecting better ranking.** It changed results in
   0 of 36 measured comparisons. It is not a semantic-search knob.
7. **Cross-check anything load-bearing against a second fetcher.** See the correctness
   warning below.

---

## ⚠ Correctness warning — verify before you trust extraction

**Status: this specific bug was fixed between 2026-08-28 and 2026-11-22. The rule it
produced still stands.**

On 2026-08-28, for both `arxiv.org/abs/2005.11401` and `arxiv.org/pdf/2005.11401`, Exa's
`/contents` returned **the correct RAG paper body with another paper's title and publication
date attached to it**:

```
# Affordance-Compiled Intelligence: Observable-Only Cognitive Impedance
  Matching for No-Meta LLM-Integrated Systems
arXiv (Cornell University). Published: 2026-03-13. Preprint. 3,030 citations.
```

Underneath that header sat the real paper — 74.3% of its distinctive sentences, verbatim,
with the correct title and author line in the body. The header's title belongs to a genuine
2026 preprint by K. Takahashi, published on **Zenodo, not arXiv**; the date is six years off.
The response was **byte-identical for the `/abs/` and `/pdf/` forms**, across all 3 repeats.
TinyFish and Firecrawl independently returned correctly-labelled text for both.

Scope: 1 collision group across 24 URLs for Exa; 0 for TinyFish.

**Why this mattered more than a wrong document.** A wrong document fails a content check.
Here the content was right, so the check passes — and an agent asking "what is this paper,
when was it published" got `2026-03-13` for a paper from May 2020. A failed fetch is visible;
**wrong metadata arrives looking exactly like right metadata** and gets ingested as fact.

**Re-checked 2026-11-22: fixed.** Exa now returns the correct title and
`arXiv:2005.11401v4 [cs.CL] 12 Apr 2021`, and the entire metadata-enrichment block the bad
header lived in — title, publication date, "Preprint", citation count, per-author h-index
figures, topic list — is gone from the response. Raw record: `raw/_recheck_20261122.json`.
It was not reported in between, so no credit is claimed for the fix.

*Still true: Exa returns byte-identical text for the `/abs/` and `/pdf/` forms. TinyFish
distinguishes them (4,846 chars vs 69,080). That is a defensible normalisation choice rather
than a bug, and it is why Exa's 20% anchor recall on arXiv abstract pages would likely still
reproduce — the ground truth for that URL is the abstract page, not the paper.*

**The rule, which does not depend on the bug:** if an extraction feeds a citation, a dataset,
or a claim you will publish, fetch it twice with different providers and compare. That is
cheap when one of the two is free.

## Cost — the real reason to route

Exa list price: $7/1k searches (≤10 results), +$1/1k for each extra result, +$1/1k pages
of text. TinyFish Search and Fetch are $0.00 at any wallet balance.

| Call pattern | Exa $/1k calls | TinyFish |
|---|---|---|
| search, 10 results, no text | $7 | $0 |
| search, 15 results + text (`kit.py` default) | $27 | $0 |
| search, 20 results + text (neural) | $37 | $0 |
| search, 25 results + text (sweep) | **$47** | $0 |
| `findSimilar`, 20 results | $17 | *not available* |
| `contents` | $1/1k pages | $0 |

On a 25-result sweep with text, the search is **$7 of $47**: 15 additional results are $15,
and text for all 25 pages is $25. **`numResults` and `text` are 85% of the bill, not the
search.** Dropping to 10 results with no text takes $47 → $7.

*Tier note: this uses `auto` at $7/1k, the configuration the calling project shipped. Exa
also lists `lite` and `instant` at $4/1k, which this benchmark did not test, so the gap above
is against Exa's $7 tier and not its cheapest. The `findSimilar` figure is derived from the
Aug 2026 list price and is no longer published on Exa's pricing page.*

TinyFish limits, re-checked 2026-11-17: **30 search req/min and 500/hour; 150 fetch URLs/min
and 1,000/day.** Still $0.00 per request at a $0 wallet balance.

⚠ **An earlier version of this file said TinyFish was "uncapped in total volume." That is no
longer true** — there is now a hard ceiling of 1,000 fetched URLs per day, and 500 searches
per hour. TinyFish's own launch post (2026-05-04) stated per-minute limits only, so these
appear to be new. "Default to TinyFish for fetch" is sound at research volume and **breaks
above 1,000 URLs/day.** Pace loops at ~2s between searches, and check current limits
yourself before migrating.

---

## Measured results

Weights reflect call frequency in this repo, not general importance.

| Suite | Metric | Exa | TinyFish | Verdict |
|---|---|---|---|---|
| **S1** known-item (25 q) | recall@20 | 98.0% | **98.0%** | **TinyFish** (101.7%) |
| | nDCG / MRR | 85.1% / 0.869 | **90.3% / 0.943** | ranks better |
| | latency p50 | **1 282 ms** | 3 645 ms | Exa 2.8× faster, 1 call vs 2 |
| **S2** discovery (12 q) | hit@10 | **50.0%** | 41.7% | **Exa** (78.4%) |
| | recall@20 | **16.7%** | 11.1% | |
| **S3** expansion (10 seeds) | new domains/seed | **8.2** | 0.3 | **Exa** (0.4%) |
| | off-domain rate | **50.1%** | 6.0% | |
| **S4** extraction (24 URLs) | success | 91.7% | 91.7% | **TinyFish** (103.0%) |
| | anchor recall | 51.4% | **55.7%** | |
| | latency p50 | **557 ms** | 1 365 ms | Exa 2.4× faster |

**Weighted total: TinyFish 88.8% of Exa** — close overall, but the average hides that
they win *different* jobs. That is why this document routes per-call and not per-vendor.

### Extraction, by page type (anchor recall)

| Page type | Exa | TinyFish |
|---|---|---|
| arXiv abstract | 20% | **100%** |
| PDF | 60% | **80%** |
| JS SPA | **86.7%** | 66.7% |
| marketing page | 80% | 80% |
| **EU cookie wall** | **26.7%** | **26.7%** |
| **soft paywall** | **0%** | **20%** |

**Both providers fail cookie walls and paywalls.** Neither is a scraping solution for
consent-gated EU sites — budget for a real browser there, or use TinyFish's paid
Browser/Agent product.

---

## Caveats — read before quoting these numbers

- **S2's absolute recall (16.7% / 11.1%) is a floor, not a real-world estimate.** The gold
  sets are hand-curated and too narrow; Exa returned real fellowships (`cbai.ai`,
  `iliad.ac`) that simply weren't on the list. Both engines faced the identical gold set,
  so the **ratio** holds and the absolute numbers understate both.
- **S3's metric was redefined after seeing data.** `findSimilar` returns similar *pages*,
  not competitor *organisations* — the original gold premise was wrong and scored 0.0%
  for both. It now measures new-domain yield. See `bench/RUBRIC.md` §9.
- **Latency was measured from India on a single connection.** Treat as directional.
- **Free is a pricing decision, not a contract** — and the terms have already moved once:
  per-hour and per-day caps appeared between 2026-08-28 and 2026-11-17. Routing keeps Exa
  integrated for two call types, which is the cheap insurance if the free tier changes again.
- **Exa was tested on `type=auto` ($7/1k), not its cheaper `lite`/`instant` tiers ($4/1k).**

---

## Snippet for `CLAUDE.md`

```markdown
## Web search routing
- Named lookups + URL fetching -> TinyFish (free; ties or beats Exa).
- Descriptive/semantic discovery -> Exa `type=neural` (TinyFish has no semantic mode).
- Lookalike expansion from a URL -> Exa `findSimilar` (no TinyFish equivalent; do not fake it).
- Always normalise URLs to `www.` before fetching — neither provider follows apex->www.
- Verify load-bearing extractions with a second provider. (In Aug 2026 Exa `/contents`
  attached another paper's title and date to the correct arXiv body; fixed by Nov 2026.)
- TinyFish free tier caps fetch at 1,000 URLs/day and search at 500/hour.
- Full rules + data: SEARCH-ROUTING.md
```
