"""Exa vs TinyFish -- deterministic scorer.

Reads bench/raw/*.jsonl and produces a scorecard. Contains NO network calls and
NO model judgement: given the same raw files and the same fixtures, this script
always prints byte-identical scores. Re-run it freely after editing the rubric.

Usage:
    python bench/score.py <run_id>            # e.g. 20260828-142530
    python bench/score.py <run_id> --json     # machine-readable scorecard
    python bench/score.py --list              # show available run ids
"""
import json, os, re, sys, glob, statistics, math

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
RAW = os.path.join(HERE, "raw")

# Weights reflect how often each surface is actually called in this repo
# (tools/kit.py + discovery-kit/harvest.py), not how interesting it is.
WEIGHTS = {"S1": 0.25, "S2": 0.30, "S3": 0.15, "S4": 0.30}

# A surface counts as replaceable when TinyFish reaches this share of Exa's score.
PARITY = 0.90

# Junk strings that mean the extractor returned chrome instead of content.
def norm_text(s):
    """Fold away formatting so anchor matching tests CONTENT, not rendering.
    PDFs are the reason this exists: the referee renders an author line as
    'Patrick Lewis††, Ethan Perez*' where another extractor gives
    'Patrick Lewis†‡, Ethan Perez⋆'. Same text, different glyphs -- exact
    substring matching scored that as a total miss."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


BOILERPLATE = ["accept all cookies", "skip to main content", "enable javascript",
               "javascript is disabled", "your browser is not supported",
               "we use cookies", "cookie settings", "privacy preference center",
               "are you a robot", "access denied", "just a moment"]


# ------------------------------------------------------------ url handling

def canon(u):
    """Scheme/www/query/fragment/trailing-slash insensitive form."""
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.split("#")[0].split("?")[0]
    return u.rstrip("/")


def host(u):
    return canon(u).split("/")[0]


def matches(h, g):
    """A result host matches a gold host if it IS that host or is a subdomain of
    it. Without the subdomain arm, `alignment.anthropic.com` -- the actual
    Anthropic Fellows page -- scores as a miss against gold `anthropic.com`."""
    return h == g or h.endswith("." + g)


def hits(urls, gold):
    """Ordered list of gold hosts matched, first occurrence wins. Host-level
    matching keeps the fixture durable across site restructures."""
    goldset = [canon(g).split("/")[0] for g in gold]
    seen, order = set(), []
    for i, u in enumerate(urls):
        h = host(u)
        for g in goldset:
            if g not in seen and matches(h, g):
                seen.add(g)
                order.append((g, i))
                break
    return order


def recall_at_k(urls, gold, k):
    return len(hits(urls[:k], gold)) / len(gold) if gold else 0.0


def mrr(urls, gold):
    h = hits(urls, gold)
    return 1.0 / (h[0][1] + 1) if h else 0.0


def hit_at_k(urls, gold, k):
    return 1.0 if hits(urls[:k], gold) else 0.0


def ndcg_at_k(urls, gold, k):
    """Binary relevance nDCG. Ideal ranking = every gold host at the top."""
    if not gold:
        return 0.0
    goldset = {canon(g).split("/")[0] for g in gold}
    seen = set()
    dcg = 0.0
    for i, u in enumerate(urls[:k]):
        h = host(u)
        if h in goldset and h not in seen:
            seen.add(h)
            dcg += 1.0 / math.log2(i + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(goldset), k)))
    return dcg / ideal if ideal else 0.0


# ---------------------------------------------------------------- plumbing

def load(suite, run_id):
    rows = []
    for p in glob.glob(os.path.join(RAW, "%s__%s*.jsonl" % (suite, run_id))):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fixture(name):
    return json.load(open(os.path.join(FIX, name + ".json"), encoding="utf-8"))


def by_variant(rows):
    """Group as {(provider, variant): {id: row}} and average duplicate reps."""
    g = {}
    for r in rows:
        g.setdefault((r["provider"], r.get("variant", "")), {}).setdefault(r["id"], []).append(r)
    return g


def lat(rows):
    v = [r["latency_ms"] for r in rows if r.get("latency_ms")]
    if not v:
        return (0.0, 0.0)
    v.sort()
    p50 = statistics.median(v)
    p95 = v[min(len(v) - 1, int(0.95 * len(v)))]
    return (p50, p95)


def pct(x):
    return "%5.1f%%" % (100 * x)


# ------------------------------------------------------------------ suites

def score_ranked(rows, items, gold_key, id_key, k, label):
    """Shared scorer for S1/S2/S3 -- they differ only in fixture shape."""
    gold = {it[id_key]: it["gold"] for it in items}
    out = {}
    for (prov, var), byid in by_variant(rows).items():
        per = []
        for qid, reps in byid.items():
            if qid not in gold:
                continue
            g = gold[qid]
            # average across repeats so a flaky run cannot swing the verdict
            per.append({
                "hit10": statistics.mean(hit_at_k(r["urls"], g, 10) for r in reps),
                "hit20": statistics.mean(hit_at_k(r["urls"], g, 20) for r in reps),
                "recall": statistics.mean(recall_at_k(r["urls"], g, k) for r in reps),
                "ndcg": statistics.mean(ndcg_at_k(r["urls"], g, k) for r in reps),
                "mrr": statistics.mean(mrr(r["urls"], g) for r in reps),
                "n": statistics.mean(len(r["urls"]) for r in reps),
                "calls": statistics.mean(r["calls"] for r in reps),
                "ok": statistics.mean(1.0 if r["ok"] else 0.0 for r in reps),
            })
        if not per:
            continue
        flat = [r for reps in byid.values() for r in reps]
        p50, p95 = lat(flat)
        out[(prov, var)] = {
            "label": label, "queries": len(per),
            "hit@10": statistics.mean(x["hit10"] for x in per),
            "hit@20": statistics.mean(x["hit20"] for x in per),
            "recall@k": statistics.mean(x["recall"] for x in per),
            "ndcg@k": statistics.mean(x["ndcg"] for x in per),
            "mrr": statistics.mean(x["mrr"] for x in per),
            "avg_results": statistics.mean(x["n"] for x in per),
            "avg_calls": statistics.mean(x["calls"] for x in per),
            "success": statistics.mean(x["ok"] for x in per),
            "p50_ms": p50, "p95_ms": p95,
        }
    return out


def score_s1(run_id):
    fx = fixture("known_item")
    return score_ranked(load("S1_known_item", run_id), fx["queries"],
                        "gold", "id", 20, "known-item")


def score_s2(run_id):
    fx = fixture("discovery")
    return score_ranked(load("S2_discovery", run_id), fx["queries"],
                        "gold", "id", fx.get("k", 20), "discovery")


def score_s3(run_id):
    """S3 was REDEFINED after the first run. The original metric assumed
    findSimilar returns sibling ORGANISATIONS; the raw data showed it returns
    similar PAGES -- 46%% of Exa's results and 91%% of the TinyFish surrogate's
    were on the seed's own domain, and gold-hit rate was 0 for both. That made
    the old metric a test of a capability neither product claims.

    The metric now measures the job harvest.py:150 actually uses this for --
    "the cheapest way to grow a seed list": how many NEW domains come back.
    Fully deterministic, and it no longer depends on my guess at who a given
    programme's competitors are."""
    fx = fixture("similar")
    seedhost = {s["id"]: host(s["url"]) for s in fx["seeds"]}
    gold = {s["id"]: s["gold"] for s in fx["seeds"]}
    out = {}
    for (prov, var), byid in by_variant(load("S3_similar", run_id)).items():
        per = []
        for sid, reps in byid.items():
            if sid not in seedhost:
                continue
            rec = []
            for r in reps:
                hs = [host(u) for u in r["urls"]]
                if not hs:
                    rec.append({"new": 0.0, "distinct": 0.0, "same": 0.0, "gold": 0.0})
                    continue
                off = [h for h in hs if not matches(h, seedhost[sid])]
                rec.append({
                    "new": len(off) / len(hs),
                    "distinct": len(set(off)),
                    "same": 1 - len(off) / len(hs),
                    "gold": 1.0 if any(matches(h, g) for h in off for g in gold[sid]) else 0.0,
                })
            per.append({k: statistics.mean(x[k] for x in rec) for k in rec[0]})
        if not per:
            continue
        flat = [r for reps in byid.values() for r in reps]
        p50, p95 = lat(flat)
        out[(prov, var)] = {
            "label": "lookalike", "seeds": len(per),
            "offdomain_rate": statistics.mean(x["new"] for x in per),
            "new_domains": statistics.mean(x["distinct"] for x in per),
            "samedomain_rate": statistics.mean(x["same"] for x in per),
            "gold_hit": statistics.mean(x["gold"] for x in per),
            "avg_calls": statistics.mean(r["calls"] for r in flat),
            "p50_ms": p50, "p95_ms": p95,
        }
    return out


def score_s4(run_id):
    """Extraction fidelity against the Firecrawl referee anchors."""
    fx = fixture("fetch")
    meta = {u["id"]: u for u in fx["urls"]}
    rows = load("S4_fetch", run_id)
    out, per_cat = {}, {}
    for (prov, var), byid in by_variant(rows).items():
        per, scorable, cats = [], [], {}
        for uid, reps in byid.items():
            m = meta.get(uid)
            if not m:
                continue
            anchors = m.get("anchors") or []
            ref = m.get("referee_chars") or 0
            rec = []
            nanch = [norm_text(s) for s in anchors]
            for r in reps:
                txt = (r.get("text") or "")
                low = txt.lower()
                ntxt = norm_text(txt)
                a = (sum(1 for s in nanch if s and s in ntxt) / len(nanch)) if nanch else 0.0
                cov = min(1.0, len(txt) / ref) if ref else 0.0
                bp = sum(1 for b in BOILERPLATE if b in low[:4000])
                rec.append({"ok": 1.0 if r["ok"] else 0.0, "anchor": a, "cov": cov,
                            "bp": bp, "chars": len(txt)})
            row = {kk: statistics.mean(x[kk] for x in rec)
                   for kk in ("ok", "anchor", "cov", "bp", "chars")}
            # success counts everywhere; anchor/coverage only where the referee
            # actually produced usable ground truth.
            per.append(row)
            if m.get("scorable"):
                scorable.append(row)
                cats.setdefault(m["category"], []).append(row)
        if not per:
            continue
        flat = [r for reps in byid.values() for r in reps]
        p50, p95 = lat(flat)
        out[(prov, var)] = {
            "label": "extraction", "urls": len(per), "scorable_urls": len(scorable),
            "success": statistics.mean(x["ok"] for x in per),
            "anchor_recall": statistics.mean(x["anchor"] for x in scorable) if scorable else 0.0,
            "coverage_vs_referee": statistics.mean(x["cov"] for x in scorable) if scorable else 0.0,
            "boilerplate_hits": statistics.mean(x["bp"] for x in per),
            "avg_chars": statistics.mean(x["chars"] for x in per),
            "p50_ms": p50, "p95_ms": p95,
        }
        per_cat[(prov, var)] = {c: {"success": statistics.mean(x["ok"] for x in v),
                                    "anchor_recall": statistics.mean(x["anchor"] for x in v)}
                                for c, v in sorted(cats.items())}
    return out, per_cat


# ------------------------------------------------------------------ report

def headline(s, sc):
    """The single number each suite contributes to the verdict."""
    if s == "S4":
        return 0.5 * sc["success"] + 0.5 * sc["anchor_recall"]
    if s == "S3":
        # Expansion yield: share of results that leave the seed domain, scaled by
        # how many distinct new domains that actually amounts to (capped at 10).
        return sc["offdomain_rate"] * min(1.0, sc["new_domains"] / 10.0)
    return 0.5 * sc["recall@k"] + 0.3 * sc["ndcg@k"] + 0.2 * sc["hit@10"]


def best(scores, provider):
    """A provider is judged on its best-performing variant -- most generous read."""
    cand = {k: v for k, v in scores.items() if k[0] == provider}
    if not cand:
        return None, None
    k = max(cand, key=lambda kk: headline(cur_suite[0], cand[kk]))
    return k, cand[k]


cur_suite = [None]


def table(title, scores, cols):
    print("\n" + title)
    print("  " + "provider/variant".ljust(24) + "".join(c[0].rjust(c[1]) for c in cols))
    for (prov, var), sc in sorted(scores.items()):
        name = ("%s/%s" % (prov, var))[:23]
        line = "  " + name.ljust(24)
        for cname, w, fmt in cols:
            line += fmt(sc).rjust(w)
        print(line)


def main():
    a = sys.argv[1:]
    if "--list" in a or not a:
        ids = sorted({os.path.basename(p).split("__")[1].replace(".jsonl", "")
                      for p in glob.glob(os.path.join(RAW, "S*__*.jsonl"))})
        print("available run ids:")
        for i in ids:
            print("  ", i)
        if not ids:
            print("   (none -- run: python bench/run_bench.py all)")
        return
    run_id = a[0]
    as_json = "--json" in a

    s1, s2, s3 = score_s1(run_id), score_s2(run_id), score_s3(run_id)
    s4, s4cat = score_s4(run_id)
    suites = {"S1": s1, "S2": s2, "S3": s3, "S4": s4}

    if as_json:
        ser = {s: {"%s/%s" % k: v for k, v in sc.items()} for s, sc in suites.items()}
        ser["_per_category_S4"] = {"%s/%s" % k: v for k, v in s4cat.items()}
        print(json.dumps(ser, indent=1))
        return

    print("=" * 78)
    print("EXA vs TINYFISH  --  run %s" % run_id)
    print("=" * 78)

    rank_cols = [("hit@10", 9, lambda s: pct(s["hit@10"])),
                 ("rec@k", 9, lambda s: pct(s["recall@k"])),
                 ("nDCG@k", 9, lambda s: pct(s["ndcg@k"])),
                 ("MRR", 8, lambda s: "%.3f" % s["mrr"]),
                 ("calls", 7, lambda s: "%.1f" % s["avg_calls"]),
                 ("p50ms", 8, lambda s: "%.0f" % s["p50_ms"])]
    for name, sc, ttl in (("S1", s1, "S1  KNOWN-ITEM RETRIEVAL"),
                          ("S2", s2, "S2  SEMANTIC DISCOVERY (precedent mining)")):
        if sc:
            table(ttl, sc, rank_cols)
    if s3:
        table("S3  LOOKALIKE EXPANSION  (metric redefined -- see score_s3 docstring)",
              s3, [("off-dom", 10, lambda s: pct(s["offdomain_rate"])),
                   ("newdoms", 10, lambda s: "%.1f" % s["new_domains"]),
                   ("same-dom", 10, lambda s: pct(s["samedomain_rate"])),
                   ("goldhit", 9, lambda s: pct(s["gold_hit"])),
                   ("calls", 7, lambda s: "%.1f" % s["avg_calls"]),
                   ("p50ms", 8, lambda s: "%.0f" % s["p50_ms"])])

    if s4:
        table("S4  CONTENT EXTRACTION",
              s4, [("success", 10, lambda s: pct(s["success"])),
                   ("anchors", 10, lambda s: pct(s["anchor_recall"])),
                   ("cover", 9, lambda s: pct(s["coverage_vs_referee"])),
                   ("junk", 7, lambda s: "%.2f" % s["boilerplate_hits"]),
                   ("chars", 9, lambda s: "%.0f" % s["avg_chars"]),
                   ("p50ms", 8, lambda s: "%.0f" % s["p50_ms"])])
        print("\n  by page category (success / anchor-recall)")
        cats = sorted({c for v in s4cat.values() for c in v})
        for c in cats:
            line = "    " + c.ljust(22)
            for k in sorted(s4cat):
                v = s4cat[k].get(c)
                line += ("%s/%s" % (k[0][:3], pct(v["anchor_recall"]).strip())).rjust(18) if v else "".rjust(18)
            print(line)

    # ------------------------------------------------------------- verdict
    print("\n" + "=" * 78)
    print("VERDICT   (TinyFish must reach %.0f%% of Exa on a surface to replace it)" % (100 * PARITY))
    print("=" * 78)
    total_e = total_t = 0.0
    verdicts = {}
    for s, sc in suites.items():
        if not sc:
            continue
        cur_suite[0] = s
        ek, ev = best(sc, "exa")
        tk, tv = best(sc, "tinyfish")
        if not ev or not tv:
            continue
        e, t = headline(s, ev), headline(s, tv)
        ratio = (t / e) if e else 0.0
        w = WEIGHTS[s]
        total_e += w * e
        total_t += w * t
        verdict = "REPLACE" if ratio >= PARITY else ("PARTIAL" if ratio >= 0.6 else "KEEP EXA")
        verdicts[s] = (ratio, verdict)
        print("  %s  w=%.2f   exa=%.3f (%s)   tinyfish=%.3f (%s)   ratio=%5.1f%%   -> %s"
              % (s, w, e, ek[1], t, tk[1], 100 * ratio, verdict))
    if total_e:
        print("\n  WEIGHTED TOTAL   exa=%.3f  tinyfish=%.3f  ratio=%.1f%%"
              % (total_e, total_t, 100 * total_t / total_e))
        keep = [s for s, (r, v) in verdicts.items() if v != "REPLACE"]
        if not keep:
            print("  => TinyFish clears parity on every surface. Safe to swap.")
        else:
            print("  => Keep Exa for: %s. TinyFish can take the rest." % ", ".join(sorted(keep)))
    print()


if __name__ == "__main__":
    main()
