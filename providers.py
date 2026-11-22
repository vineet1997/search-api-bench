"""Provider adapters for the Exa-vs-TinyFish bench.

Every adapter returns the SAME shape so the scorer never knows which provider
produced a row:

    search  -> {"ok":bool, "latency_ms":float, "calls":int, "urls":[str],
                "rows":[{"title","url","snippet","published"}], "error":str|None}
    fetch   -> {"ok":bool, "latency_ms":float, "calls":int,
                "text":str, "error":str|None}

The Exa payloads mirror the configuration the calling project actually shipped,
deliberately: this benchmarks the config in production use, not a tuned one.
"""
import os, sys, time, json
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
# Works whether this file sits at a repo root (.env.local beside it) or one level down.
ROOT = HERE if os.path.exists(os.path.join(HERE, ".env.local")) else os.path.dirname(HERE)


def env(k):
    """Minimal .env.local reader -- no dependency on python-dotenv."""
    for line in open(os.path.join(ROOT, ".env.local"), encoding="utf-8"):
        line = line.strip()
        if line.startswith(k + "="):
            return line.split("=", 1)[1]
    raise KeyError(k)


def _timed(fn):
    t = time.perf_counter()
    try:
        out = fn()
        return out, (time.perf_counter() - t) * 1000, None
    except Exception as e:
        return None, (time.perf_counter() - t) * 1000, "%s: %s" % (type(e).__name__, e)


def _exa_headers():
    return {"x-api-key": env("EXA_API_KEY")}


# --------------------------------------------------------------------- EXA

def exa_search(query, n=20, kind="auto", text=True):
    """Mirror of tools/kit.py:exa()."""
    def call():
        payload = {"query": query, "numResults": n, "type": kind}
        if text:
            payload["contents"] = {"text": {"maxCharacters": 2000}}
        r = requests.post("https://api.exa.ai/search", json=payload,
                          headers=_exa_headers(), timeout=90)
        r.raise_for_status()
        return r.json().get("results", [])
    res, ms, err = _timed(call)
    if err:
        return {"ok": False, "latency_ms": ms, "calls": 1, "urls": [],
                "rows": [], "error": err}
    rows = [{"title": x.get("title"), "url": x.get("url"),
             "snippet": (x.get("text") or "")[:2000],
             "published": x.get("publishedDate")} for x in res]
    return {"ok": True, "latency_ms": ms, "calls": 1,
            "urls": [r["url"] for r in rows], "rows": rows, "error": None}


def exa_similar(url, n=20):
    """Mirror of tools/kit.py:exa_similar()."""
    def call():
        r = requests.post("https://api.exa.ai/findSimilar",
                          json={"url": url, "numResults": n},
                          headers=_exa_headers(), timeout=90)
        r.raise_for_status()
        return r.json().get("results", [])
    res, ms, err = _timed(call)
    if err:
        return {"ok": False, "latency_ms": ms, "calls": 1, "urls": [],
                "rows": [], "error": err}
    rows = [{"title": x.get("title"), "url": x.get("url"),
             "snippet": "", "published": None} for x in res]
    return {"ok": True, "latency_ms": ms, "calls": 1,
            "urls": [r["url"] for r in rows], "rows": rows, "error": None}


def exa_fetch(url, chars=100000):
    """Mirror of tools/kit.py:exa_contents(), single URL."""
    def call():
        r = requests.post("https://api.exa.ai/contents",
                          json={"urls": [url], "text": {"maxCharacters": chars}},
                          headers=_exa_headers(), timeout=120)
        r.raise_for_status()
        return r.json().get("results", [])
    res, ms, err = _timed(call)
    if err:
        return {"ok": False, "latency_ms": ms, "calls": 1, "text": "", "error": err}
    txt = (res[0].get("text") or "") if res else ""
    return {"ok": bool(txt), "latency_ms": ms, "calls": 1, "text": txt,
            "error": None if txt else "empty_text"}


# ---------------------------------------------------------------- TINYFISH

_TF = None


def tf_client():
    global _TF
    if _TF is None:
        from tinyfish import TinyFish
        _TF = TinyFish(api_key=env("TINYFISH_API_KEY"))
    return _TF


def tf_search(query, n=20, domain_type=None, purpose=None):
    """TinyFish returns a fixed 10 results/page, so reaching n needs pagination.
    Extra pages are counted in `calls` -- that is a real cost of parity."""
    pages = max(1, -(-n // 10))
    rows, calls, err = [], 0, None
    t = time.perf_counter()
    for p in range(pages):
        try:
            kw = {"page": p}
            if domain_type:
                kw["domain_type"] = domain_type
            if purpose:
                kw["purpose"] = purpose
            r = tf_client().search.query(query, **kw)
            calls += 1
            for x in r.results:
                rows.append({"title": x.title, "url": x.url,
                             "snippet": x.snippet or "",
                             "published": getattr(x, "date", None)})
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
            break
        if p < pages - 1:
            time.sleep(2.0)          # 30 req/min documented ceiling
    ms = (time.perf_counter() - t) * 1000
    rows = rows[:n]
    return {"ok": bool(rows), "latency_ms": ms, "calls": calls,
            "urls": [r["url"] for r in rows], "rows": rows,
            "error": err if not rows else None}


def tf_fetch(url, fmt="markdown"):
    def call():
        return tf_client().fetch.get_contents([url], format=fmt, ttl=0)
    res, ms, err = _timed(call)
    if err:
        return {"ok": False, "latency_ms": ms, "calls": 1, "text": "", "error": err}
    if res.errors:
        e = res.errors[0]
        return {"ok": False, "latency_ms": ms, "calls": 1, "text": "",
                "error": str(getattr(e, "error", e))}
    txt = (res.results[0].text or "") if res.results else ""
    if not isinstance(txt, str):
        txt = json.dumps(txt)
    return {"ok": bool(txt), "latency_ms": ms, "calls": 1, "text": txt,
            "error": None if txt else "empty_text"}


def tf_similar_surrogate(url, n=20):
    """TinyFish has no findSimilar. Best-effort stand-in, so the gap is measured
    rather than assumed: pull the seed page's outbound links, then run one search
    built from the seed's own title. Counts every call it costs."""
    rows, calls, err = [], 0, None
    t = time.perf_counter()
    title = ""
    try:
        r = tf_client().fetch.get_contents([url], format="markdown", links=True, ttl=0)
        calls += 1
        if r.results:
            title = r.results[0].title or ""
            for lk in (r.results[0].links or []):
                rows.append({"title": "", "url": lk, "snippet": "", "published": None})
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    if title:
        time.sleep(2.0)
        s = tf_search(title, n=n)
        calls += s["calls"]
        rows.extend(s["rows"])
    ms = (time.perf_counter() - t) * 1000
    seen, ded = set(), []
    for r in rows:
        if r["url"] and r["url"] not in seen:
            seen.add(r["url"])
            ded.append(r)
    ded = ded[:n]
    return {"ok": bool(ded), "latency_ms": ms, "calls": calls,
            "urls": [r["url"] for r in ded], "rows": ded,
            "error": err if not ded else None}


# ------------------------------------------------------- FIRECRAWL referee

def firecrawl_fetch(url):
    """Neutral third party used only to BUILD ground-truth anchors. Never scored."""
    def call():
        r = requests.post("https://api.firecrawl.dev/v1/scrape",
                          json={"url": url, "formats": ["markdown"]},
                          headers={"Authorization": "Bearer " + env("FIRECRAWL_API_KEY"),
                                   "Content-Type": "application/json"}, timeout=180)
        r.raise_for_status()
        return r.json().get("data", {}).get("markdown", "") or ""
    res, ms, err = _timed(call)
    return {"ok": bool(res), "latency_ms": ms, "calls": 1,
            "text": res or "", "error": err}
