# Raw records

Every number in [`../README.md`](../README.md) and
[`../SEARCH-ROUTING.md`](../SEARCH-ROUTING.md) is derived from these files by
[`../score.py`](../score.py), which makes no network calls. Re-score for free:

    python score.py 20260828-124047

## What's here

- `S1_known_item__20260828-124047-r{1,2,3}.jsonl` — known-item retrieval, 3 repeats
- `S2_discovery__20260828-124047-r{1,2,3}.jsonl` — semantic discovery, 3 repeats
- `S3_similar__20260828-124047-r{1,2,3}.jsonl` — lookalike expansion, 3 repeats
- `S4_fetch__20260828-124047-r{1,2,3}.jsonl` — content extraction, 3 repeats
- `S4_referee.jsonl` — the Firecrawl referee pass that produced S4 ground truth
- `_run.log`, `_build_anchors.log`, `_verify_gold.log` — run provenance
- `_recheck_20261122.json` — the 2026-11-22 re-check of the arXiv metadata finding

462 records in total, from 657 provider API calls, collected 2026-08-28.

## Third-party content

Records contain verbatim page text captured on 2026-08-28 from the URLs named in each
record, retained so the extraction scores can be independently verified. It is published
for measurement and reproducibility, attributed by URL throughout. If you own one of these
pages and would like a record removed, open an issue and it will be removed.
