"""Exa vs TinyFish -- benchmark runner.

This script ONLY collects evidence. It makes no judgements: every raw response
is appended to bench/raw/<suite>.jsonl and scoring happens in bench/score.py.
That split matters -- you can re-score a run with a corrected rubric without
spending a single API call again.

Usage:
    python bench/run_bench.py verify-gold      # check fixtures are still valid  (no scoring)
    python bench/run_bench.py build-anchors    # derive S4 ground truth from Firecrawl referee
    python bench/run_bench.py all              # run S1-S4 for both providers
    python bench/run_bench.py s1 s2            # run selected suites
    python bench/run_bench.py all --dry-run    # print the plan + call/cost budget, call nothing

Flags:
    --dry-run     plan only, zero network calls
    --repeat N    repeat each suite N times (default 1; use 3 for latency stability)
    --limit N     only the first N items of each fixture (smoke runs)
"""
import json, os, sys, time, datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
RAW = os.path.join(HERE, "raw")
os.makedirs(RAW, exist_ok=True)

import providers as P   # noqa: E402  (path set by being run from bench/)

N = 20                  # results requested per query, both providers
SEARCH_PAUSE = 2.0      # TinyFish documents 30 req/min; pace under it
FETCH_PAUSE = 0.5


def fixture(name):
    return json.load(open(os.path.join(FIX, name + ".json"), encoding="utf-8"))


def out(suite, run_id):
    return os.path.join(RAW, "%s__%s.jsonl" % (suite, run_id))


def emit(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


# ------------------------------------------------------------------ suites

def run_s1(run_id, limit, dry):
    """Known-item retrieval. Exa type=auto (what kit.py ships) vs TinyFish web."""
    fx = fixture("known_item")
    qs = fx["queries"][:limit] if limit else fx["queries"]
    path = out("S1_known_item", run_id)
    for i, q in enumerate(qs):
        if dry:
            print("  S1 %s exa_search(auto) + tf_search  q=%r" % (q["id"], q["q"][:50]))
            continue
        e = P.exa_search(q["q"], n=N, kind="auto", text=True)
        emit(path, {"suite": "S1", "id": q["id"], "query": q["q"],
                    "provider": "exa", "variant": "auto", **e})
        time.sleep(SEARCH_PAUSE)
        t = P.tf_search(q["q"], n=N)
        emit(path, {"suite": "S1", "id": q["id"], "query": q["q"],
                    "provider": "tinyfish", "variant": "web", **t})
        time.sleep(SEARCH_PAUSE)
        print("  S1 %s/%s %s exa=%d tf=%d" % (i + 1, len(qs), q["id"],
                                              len(e["urls"]), len(t["urls"])))


def run_s2(run_id, limit, dry):
    """Semantic discovery. Exa type=neural (the precedent-mining mode) vs the
    only mode TinyFish has. Also records TinyFish WITH `purpose` set, since that
    is its nearest answer to intent-aware search."""
    fx = fixture("discovery")
    qs = fx["queries"][:limit] if limit else fx["queries"]
    path = out("S2_discovery", run_id)
    for i, q in enumerate(qs):
        if dry:
            print("  S2 %s exa_search(neural) + tf_search + tf_search(purpose)  q=%r"
                  % (q["id"], q["q"][:50]))
            continue
        e = P.exa_search(q["q"], n=N, kind="neural", text=True)
        emit(path, {"suite": "S2", "id": q["id"], "query": q["q"],
                    "provider": "exa", "variant": "neural", **e})
        time.sleep(SEARCH_PAUSE)
        t = P.tf_search(q["q"], n=N)
        emit(path, {"suite": "S2", "id": q["id"], "query": q["q"],
                    "provider": "tinyfish", "variant": "plain", **t})
        time.sleep(SEARCH_PAUSE)
        tp = P.tf_search(q["q"], n=N,
                         purpose="Find official program pages for research "
                                 "fellowships, residencies and visiting-researcher "
                                 "positions that match this description.")
        emit(path, {"suite": "S2", "id": q["id"], "query": q["q"],
                    "provider": "tinyfish", "variant": "purpose", **tp})
        time.sleep(SEARCH_PAUSE)
        print("  S2 %s/%s %s exa=%d tf=%d tf+purpose=%d"
              % (i + 1, len(qs), q["id"], len(e["urls"]), len(t["urls"]), len(tp["urls"])))


def run_s3(run_id, limit, dry):
    """Lookalike expansion. Exa findSimilar vs the TinyFish surrogate."""
    fx = fixture("similar")
    seeds = fx["seeds"][:limit] if limit else fx["seeds"]
    path = out("S3_similar", run_id)
    for i, s in enumerate(seeds):
        if dry:
            print("  S3 %s exa_similar + tf_similar_surrogate  %s" % (s["id"], s["url"][:50]))
            continue
        e = P.exa_similar(s["url"], n=N)
        emit(path, {"suite": "S3", "id": s["id"], "seed": s["url"],
                    "provider": "exa", "variant": "findSimilar", **e})
        time.sleep(SEARCH_PAUSE)
        t = P.tf_similar_surrogate(s["url"], n=N)
        emit(path, {"suite": "S3", "id": s["id"], "seed": s["url"],
                    "provider": "tinyfish", "variant": "surrogate", **t})
        time.sleep(SEARCH_PAUSE)
        print("  S3 %s/%s %s exa=%d tf=%d" % (i + 1, len(seeds), s["id"],
                                              len(e["urls"]), len(t["urls"])))


def run_s4(run_id, limit, dry):
    """Content extraction. Exa /contents vs TinyFish /fetch on the same URLs."""
    fx = fixture("fetch")
    if not fx.get("anchors_built") and not dry:
        sys.exit("S4 needs ground truth first:  python bench/run_bench.py build-anchors")
    us = fx["urls"][:limit] if limit else fx["urls"]
    path = out("S4_fetch", run_id)
    for i, u in enumerate(us):
        if dry:
            print("  S4 %s exa_fetch + tf_fetch  %s" % (u["id"], u["url"][:55]))
            continue
        e = P.exa_fetch(u["url"])
        emit(path, {"suite": "S4", "id": u["id"], "url": u["url"],
                    "category": u["category"], "provider": "exa",
                    "variant": "contents", **e})
        time.sleep(FETCH_PAUSE)
        t = P.tf_fetch(u["url"])
        emit(path, {"suite": "S4", "id": u["id"], "url": u["url"],
                    "category": u["category"], "provider": "tinyfish",
                    "variant": "fetch", **t})
        time.sleep(FETCH_PAUSE)
        print("  S4 %s/%s %s exa=%d chars tf=%d chars"
              % (i + 1, len(us), u["id"], len(e["text"]), len(t["text"])))


SUITES = {"s1": run_s1, "s2": run_s2, "s3": run_s3, "s4": run_s4}


# ------------------------------------------------------------- maintenance

def build_anchors():
    """Populate S4 ground truth from Firecrawl -- a THIRD provider, so neither
    contestant defines what correct extraction looks like. Anchors are the
    longest distinctive sentences of the referee text."""
    fx = fixture("fetch")
    ref_path = os.path.join(RAW, "S4_referee.jsonl")
    open(ref_path, "w", encoding="utf-8").close()
    built = 0
    for u in fx["urls"]:
        r = P.firecrawl_fetch(u["url"])
        emit(ref_path, {"id": u["id"], "url": u["url"], **r})
        if not r["ok"]:
            print("  REFEREE FAIL %s %s -> %s" % (u["id"], u["url"][:45], r["error"]))
            u["anchors"] = []
            u["referee_chars"] = 0
            continue
        sents = [s.strip() for s in r["text"].replace("\n", " ").split(". ")]
        cand = [s for s in sents if 60 <= len(s) <= 220 and not s.startswith(("!", "[", "|", "#"))]
        cand.sort(key=len, reverse=True)
        u["anchors"] = cand[:5]
        u["referee_chars"] = len(r["text"])
        built += 1
        print("  anchors %s %-45s %d anchors, %d chars"
              % (u["id"], u["url"][:45], len(u["anchors"]), u["referee_chars"]))
        time.sleep(1.0)
    fx["anchors_built"] = True
    fx["anchors_built_at"] = stamp()
    json.dump(fx, open(os.path.join(FIX, "fetch.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print("built anchors for %d/%d urls" % (built, len(fx["urls"])))


def verify_gold():
    """A benchmark is only as good as its fixtures. Confirm every gold host still
    resolves and still looks like the program it claims to be, using the free
    TinyFish fetch so verification costs nothing."""
    bad = []
    hosts = set()
    for name, key in (("known_item", "queries"), ("discovery", "queries"),
                      ("similar", "seeds")):
        for item in fixture(name)[key]:
            hosts.update(item["gold"])
    hosts = sorted(hosts)
    print("verifying %d distinct gold hosts" % len(hosts))
    for i, h in enumerate(hosts):
        # Neither provider follows an apex -> www redirect, so a bare apex 404 is a
        # quirk of the probe, not evidence the host is dead. Try www before judging.
        r = P.tf_fetch("https://" + h + "/")
        used = h
        if not (r["ok"] and len(r["text"]) > 200) and not h.startswith("www."):
            time.sleep(FETCH_PAUSE)
            r2 = P.tf_fetch("https://www." + h + "/")
            if r2["ok"] and len(r2["text"]) > 200:
                r, used = r2, "www." + h
        status = "OK  " if r["ok"] and len(r["text"]) > 200 else "DEAD"
        if status == "DEAD":
            bad.append((h, r["error"]))
        print("  [%2d/%2d] %s %-45s %6d chars %s"
              % (i + 1, len(hosts), status, h, len(r["text"]),
                 "(via www)" if used != h else ""))
        time.sleep(FETCH_PAUSE)
    print()
    if bad:
        print("!! %d gold hosts need attention before you trust a run:" % len(bad))
        for h, e in bad:
            print("   -", h, "->", e)
    else:
        print("all gold hosts live")


# -------------------------------------------------------------------- main

def plan(suites, repeat, limit):
    fx_n = {"s1": len(fixture("known_item")["queries"]),
            "s2": len(fixture("discovery")["queries"]),
            "s3": len(fixture("similar")["seeds"]),
            "s4": len(fixture("fetch")["urls"])}
    if limit:
        fx_n = {k: min(v, limit) for k, v in fx_n.items()}
    # per item: (exa calls, tinyfish calls)  -- tf search needs N/10 pages
    pages = max(1, -(-N // 10))
    per = {"s1": (1, pages), "s2": (1, 2 * pages), "s3": (1, 1 + pages), "s4": (1, 1)}
    exa_total = tf_total = 0
    print("PLAN  N=%d results/query  repeat=%d" % (N, repeat))
    for s in suites:
        n = fx_n[s]
        e, t = per[s]
        e, t = e * n * repeat, t * n * repeat
        exa_total += e
        tf_total += t
        print("  %s  items=%-3d  exa_calls=%-4d  tinyfish_calls=%-4d" % (s.upper(), n, e, t))
    print()
    print("  TOTAL exa calls      : %d" % exa_total)
    print("  TOTAL tinyfish calls : %d  (free: $0.00)" % tf_total)
    print("  Exa cost             : check your plan's per-request rate; searches with")
    print("                         contents are billed above bare searches.")
    print("  TinyFish rate ceiling: 30 search/min, 150 fetch urls/min -> runner paces at %.1fs" % SEARCH_PAUSE)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    cmd = a[0]
    dry = "--dry-run" in a
    repeat = int(a[a.index("--repeat") + 1]) if "--repeat" in a else 1
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 0

    if cmd == "build-anchors":
        return build_anchors()
    if cmd == "verify-gold":
        return verify_gold()

    suites = list(SUITES) if cmd == "all" else [x for x in a if x in SUITES]
    if not suites:
        print("nothing to run; pass all|s1|s2|s3|s4")
        return
    plan(suites, repeat, limit)
    if dry:
        print("\n-- dry run, no calls made --\n")
    run_id = stamp()
    for rep in range(repeat):
        for s in suites:
            rid = run_id if repeat == 1 else "%s-r%d" % (run_id, rep + 1)
            print("\n== %s (rep %d/%d) -> raw/%s__%s.jsonl" % (s.upper(), rep + 1, repeat,
                                                              {"s1": "S1_known_item",
                                                               "s2": "S2_discovery",
                                                               "s3": "S3_similar",
                                                               "s4": "S4_fetch"}[s], rid))
            SUITES[s](rid, limit, dry)
    if not dry:
        print("\ndone. score with:  python bench/score.py %s" % run_id)


if __name__ == "__main__":
    main()
