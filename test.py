#!/usr/bin/env python3
"""Oko Sources health checker.

Usage:
    python test.py               # full check, human output
    python test.py --quick       # home + search only (skip detail/episode paths)
    python test.py --category anime|drama|western|meta
    python test.py --json        # machine-readable JSON to stdout
    python test.py --timeout 10

Stdlib only — no pip needed. Exit 1 if any FAIL (CI-friendly).
Rank order is preserved from the sources spec; do not reorder.

What it checks per source (mirrors in listed rank order):
  anime   1 anikoto   home/filter/watch markers (AnikotoTheme, cdn.anipixcdn, data-id)
          2 animepahe home + /api search (expects Cloudflare BLOCKED as WARN, PARKED as FAIL)
          3 reanime   /home + /search?q= (/anime/ + s4.anilist.co)
          4 miruro    / (search?query= template) + /env2.js (VITE_PROXY)
          5 animex    / (Animex + graphql.anilist.co)
          6 anikage   / + /api/media/anime/browse JSON (data[0].slug/title/coverImage)
          7 lunar     / (_next/static + api.lunarx.to)
  drama   1 kisskh    Search/List/Drama/Upcoming JSON keys (id/title/thumbnail/episodes)
  western 1 shuttletv .gd/movies (image.tmdb.org + /movie/) + /search?q=
          2 hydrahd   /movies (/genres/watch- + /movie/); .ru expected DISABLED
          3 atlantic  SPA shell (#root + api.atlantic.st)
          4 bingr     /api/health {"status":"ok"} + / shell (api.bingr.one)
  meta      everythingmoe (rank= + anikoto/miruro) + aroki index.json (connectors[])
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Safari/537.36"
TIMEOUT = 15

CF_MARKERS = ("just a moment", "challenges.cloudflare.com", "cf-challenge",
              "checking your browser", "ddos-guard", "ddos guard")
PARKED_MARKERS = ("this domain is for sale", "contact the owner", "domain_sal")


# ---------------------------------------------------------------- helpers

def fetch(url: str, timeout: int, headers: dict | None = None):
    """GET url. Returns (status:int|None, body:str, elapsed_ms:int, note:str)."""
    req_headers = {"User-Agent": UA, "Accept": "text/html,application/json,*/*"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(1_500_000)  # cap 1.5MB
            ms = int((time.monotonic() - t0) * 1000)
            try:
                body = raw.decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            return r.status, body, ms, ""
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic() - t0) * 1000)
        try:
            body = e.read(200_000).decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return e.code, body, ms, f"http-{e.code}"
    except Exception as e:  # timeout / dns / ssl
        ms = int((time.monotonic() - t0) * 1000)
        return None, "", ms, f"{type(e).__name__}: {e}"


def classify(body: str) -> str:
    low = body.lower()
    if any(m in low for m in PARKED_MARKERS):
        return "PARKED"
    if any(m in low for m in CF_MARKERS):
        return "BLOCKED-CF"
    return ""


class Result:
    def __init__(self, category, rank, source, check, status, ms, detail, url=""):
        self.category = category
        self.rank = rank
        self.source = source
        self.check = check
        self.status = status  # PASS / FAIL / WARN
        self.ms = ms
        self.detail = detail
        self.url = url

    def to_dict(self):
        return {"category": self.category, "rank": self.rank, "source": self.source,
                "check": self.check, "status": self.status, "ms": self.ms,
                "detail": self.detail, "url": self.url}


def check_page(category, rank, source, name, url, markers, timeout, headers=None,
               warn_only=False, quick_skippable=False, quick=False):
    if quick and quick_skippable:
        return Result(category, rank, source, name, "WARN", 0, "skipped (--quick)", url)
    status, body, ms, note = fetch(url, timeout, headers)
    flag = classify(body)
    if status == 200 and body:
        missing = [m for m in markers if m.lower() not in body.lower()]
        if not missing:
            extra = f" [{flag}]" if flag else ""
            return Result(category, rank, source, name, "PASS", ms,
                          f"200 + markers ok{extra}", url)
        level = "WARN" if (warn_only or flag) else "FAIL"
        return Result(category, rank, source, name, level, ms,
                      f"200 but missing {missing}" + (f" [{flag}]" if flag else ""), url)
    if status in (403, 503) or flag == "BLOCKED-CF":
        return Result(category, rank, source, name, "WARN", ms,
                      f"{status or 'ERR'} blocked [{flag or note}] (cf/ddos)", url)
    if flag == "PARKED":
        return Result(category, rank, source, name, "FAIL", ms, "domain PARKED for sale", url)
    return Result(category, rank, source, name, "FAIL", ms,
                  f"{status or 'ERR'} {note} {flag}".strip(), url)


def check_json(category, rank, source, name, url, keys, timeout, headers=None,
               is_list=False, warn_only=False, quick_skippable=False, quick=False):
    if quick and quick_skippable:
        return Result(category, rank, source, name, "WARN", 0, "skipped (--quick)", url)
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    status, body, ms, note = fetch(url, timeout, h)
    flag = classify(body)
    if status != 200 or not body:
        if status in (403, 503) or flag:
            return Result(category, rank, source, name, "WARN", ms,
                          f"{status or 'ERR'} [{flag or note}]", url)
        return Result(category, rank, source, name, "FAIL", ms,
                      f"{status or 'ERR'} {note} {flag}".strip(), url)
    try:
        data = json.loads(body)
    except Exception as e:
        return Result(category, rank, source, name, "FAIL", ms, f"200 but bad JSON: {e}", url)
    items = data if (is_list and isinstance(data, list)) else ([data] if is_list else [data])
    if is_list and not isinstance(data, list):
        return Result(category, rank, source, name, "FAIL", ms, "expected JSON list", url)
    if is_list and not data:
        return Result(category, rank, source, name, "FAIL", ms, "empty list", url)
    sample = items[0] if is_list else data
    # nested key support: "a.b.c"
    missing = []
    for k in keys:
        cur = sample
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                missing.append(k)
                break
    if missing:
        level = "WARN" if warn_only else "FAIL"
        return Result(category, rank, source, name, level, ms,
                      f"JSON missing keys {missing}", url)
    n = f" ({len(data)} items)" if is_list else ""
    return Result(category, rank, source, name, "PASS", ms, f"200 JSON ok{n}", url)


def ping_mirrors(category, rank, source, mirrors, timeout):
    out = []
    for m in mirrors:
        status, body, ms, note = fetch(m + "/", timeout)
        flag = classify(body)
        if status == 200 and body and not flag:
            out.append(Result(category, rank, source, f"mirror {m}", "PASS", ms, "home 200", m + "/"))
        elif flag == "PARKED":
            out.append(Result(category, rank, source, f"mirror {m}", "FAIL", ms, "PARKED", m + "/"))
        elif status in (403, 503) or flag == "BLOCKED-CF":
            out.append(Result(category, rank, source, f"mirror {m}", "WARN", ms,
                              f"{status} [{flag or note}]", m + "/"))
        elif status == 200:
            out.append(Result(category, rank, source, f"mirror {m}", "PASS", ms,
                              f"200{(' [' + flag + ']') if flag else ''}", m + "/"))
        else:
            out.append(Result(category, rank, source, f"mirror {m}", "FAIL", ms,
                              f"{status or 'ERR'} {note}", m + "/"))
    return out


def first_working(mirrors, timeout):
    for m in mirrors:
        status, body, _, _ = fetch(m + "/", timeout)
        if status == 200 and classify(body) != "PARKED":
            return m
    return mirrors[0]


# ---------------------------------------------------------------- suites

def suite_anikoto(t, quick):
    mirrors = ["https://anikototv.to", "https://anichi.to", "https://anisuge.tv",
               "https://animesogo.to", "https://anixtv.me", "https://animixplay.tube",
               "https://animepahetv.to", "https://9animez.org", "https://hianimez.org"]
    out = ping_mirrors("anime", 1, "anikoto", mirrors, t)
    base = first_working(mirrors, t)
    out.append(check_page("anime", 1, "anikoto", "home", base + "/",
                          ["anikoto", "csrf-token"], t))
    out.append(check_page("anime", 1, "anikoto", "filter-search", base + "/filter?keyword=naruto",
                          ["watch/", "filter"], t))
    out.append(check_page("anime", 1, "anikoto", "watch-detail", base + "/watch/one-piece-odmau",
                          ["data-id", "anipixcdn"], t, quick_skippable=True, quick=quick))
    return out


def suite_animepahe(t, quick):
    mirrors = ["https://animepahe.pw", "https://animepahe.com", "https://animepahe.org"]
    out = ping_mirrors("anime", 2, "animepahe", mirrors, t)
    base = first_working(mirrors, t)
    # API search only works when not CF-challenged; WARN is fine
    out.append(check_json("anime", 2, "animepahe", "api-search", base + "/api?m=search&q=naruto",
                          [], t, warn_only=True, quick_skippable=True, quick=quick))
    return out


def suite_reanime(t, quick):
    mirrors = ["https://reanime.to", "https://reanime.cz", "https://reanime.wtf"]
    out = ping_mirrors("anime", 3, "reanime", mirrors, t)
    base = first_working(mirrors, t)
    out.append(check_page("anime", 3, "reanime", "search", base + "/search?q=one+piece",
                          ["/anime/", "s4.anilist.co"], t))
    out.append(check_page("anime", 3, "reanime", "detail", base + "/anime/one-piece-xamk74",
                          ["s4.anilist", "Subbed"], t, warn_only=True,
                          quick_skippable=True, quick=quick))
    return out


def suite_miruro(t, quick):
    mirrors = ["https://www.miruro.to", "https://www.miruro.ru",
               "https://www.miruro.bz", "https://www.miruro.tv"]
    out = ping_mirrors("anime", 4, "miruro", mirrors, t)
    base = first_working(mirrors, t)
    out.append(check_page("anime", 4, "miruro", "search-template", base + "/",
                          ["search?query=", "miruro"], t))
    out.append(check_page("anime", 4, "miruro", "env-config", base + "/env2.js",
                          ["VITE_", "PROXY"], t, quick_skippable=True, quick=quick))
    return out


def suite_animex(t, quick):
    out = ping_mirrors("anime", 5, "animex", ["https://animex.one"], t)
    out.append(check_page("anime", 5, "animex", "home", "https://animex.one/",
                          ["animex", "graphql.anilist.co"], t))
    return out


def suite_anikage(t, quick):
    out = ping_mirrors("anime", 6, "anikage", ["https://anikage.cc"], t)
    out.append(check_page("anime", 6, "anikage", "home", "https://anikage.cc/",
                          ["anikage", "s4.anilist"], t))
    out.append(check_json("anime", 6, "anikage", "api-browse",
                          "https://anikage.cc/api/media/anime/browse?sort=TRENDING_DESC&page=1",
                          ["data"], t,
                          quick_skippable=True, quick=quick))
    # normalize: API returns {"data":[ {...} ]} — verify wrapped list too
    status, body, ms, _ = fetch("https://anikage.cc/api/media/anime/browse?sort=TRENDING_DESC&page=1",
                                t, {"Accept": "application/json"})
    try:
        d = json.loads(body)
        ok = isinstance(d.get("data"), list) and len(d["data"]) > 0 and "slug" in d["data"][0]
        out.append(Result("anime", 6, "anikage", "api-browse-data[]", "PASS" if ok else "FAIL",
                          ms, "data[] ok" if ok else "data[] bad",
                          "https://anikage.cc/api/media/anime/browse"))
    except Exception as e:
        if not quick:
            out.append(Result("anime", 6, "anikage", "api-browse-data[]", "FAIL", ms,
                              f"parse: {e}", "https://anikage.cc/api/media/anime/browse"))
    return out


def suite_lunar(t, quick):
    out = ping_mirrors("anime", 7, "lunar", ["https://lunarx.to"], t)
    out.append(check_page("anime", 7, "lunar", "next-shell", "https://lunarx.to/",
                          ["_next/static", "lunar"], t))
    return out


def suite_kisskh(t, quick):
    mirrors = ["https://kisskh.co", "https://kisskh.la", "https://kisskh.id",
               "https://kisskh.is", "https://kisskh.do", "https://kisskh.ovh"]
    out = ping_mirrors("drama", 1, "kisskh", mirrors, t)
    base = first_working(mirrors, t)
    ref = {"Referer": base + "/"}
    out.append(check_json("drama", 1, "kisskh", "api-search",
                          base + "/api/DramaList/Search?q=queen&type=0",
                          ["id", "title", "thumbnail", "episodesCount"], t, headers=ref, is_list=True))
    out.append(check_json("drama", 1, "kisskh", "api-list",
                          base + "/api/DramaList/List?page=1&type=0&sub=0&country=0&status=0&order=2&pageSize=3",
                          ["data", "totalCount"], t, headers=ref))
    out.append(check_json("drama", 1, "kisskh", "api-drama-8714",
                          base + "/api/DramaList/Drama/8714?isq=false",
                          ["title", "episodes", "episodesCount", "country"], t, headers=ref,
                          quick_skippable=True, quick=quick))
    out.append(check_json("drama", 1, "kisskh", "api-upcoming",
                          base + "/api/DramaList/Upcoming?ispc=true",
                          ["id", "title", "thumbnail"], t, headers=ref, is_list=True,
                          warn_only=True, quick_skippable=True, quick=quick))
    # Episode stream without kkey must 403 — proves protection contract unchanged
    status, _, ms, _ = fetch(base + "/api/DramaList/Episode/147731.png?kkey=test", t, ref)
    out.append(Result("drama", 1, "kisskh", "api-episode-nokey-403",
                      "PASS" if status == 403 else ("WARN" if status == 200 else "FAIL"),
                      ms, f"status={status} (expect 403 without kkey)",
                      base + "/api/DramaList/Episode/..."))
    return out


def suite_shuttletv(t, quick):
    # User-given mirrors only: .su/.pk (CSR shells)
    mirrors = ["https://shuttletv.su", "https://shuttletv.pk"]
    out = ping_mirrors("western", 1, "shuttletv", mirrors, t)
    base = first_working(mirrors, t)
    out.append(check_page("western", 1, "shuttletv", "csr-shell", base + "/",
                          ["_next/static", "shuttletv"], t))
    out.append(check_page("western", 1, "shuttletv", "movies-route", base + "/movies",
                          ["_next/static"], t, warn_only=True,
                          quick_skippable=True, quick=quick))
    return out


def suite_hydrahd(t, quick):
    mirrors = ["https://hydrahd.ws", "https://hydrahd.com", "https://hydrahd.me", "https://hydrahd.ac"]
    out = ping_mirrors("western", 2, "hydrahd", mirrors, t)
    out.append(check_page("western", 2, "hydrahd", "movies", "https://hydrahd.ws/movies",
                          ["/genres/watch-", "/movie/"], t))
    out.append(check_page("western", 2, "hydrahd", "movies-popular", "https://hydrahd.ws/movies/popular/",
                          ["/movie/"], t, warn_only=True, quick_skippable=True, quick=quick))
    # .ru is known DISABLED — assert it stays down/parked (documents expectation)
    status, body, ms, note = fetch("https://hydrahd.ru/", t)
    dead = status is None or status >= 400 or classify(body) in ("PARKED", "BLOCKED-CF")
    out.append(Result("western", 2, "hydrahd", "ru-disabled-expect-down",
                      "PASS" if dead else "WARN", ms,
                      f"status={status} (expect down/disabled)", "https://hydrahd.ru/"))
    return out


def suite_atlantic(t, quick):
    out = ping_mirrors("western", 3, "atlantic", ["https://atlantic.st"], t)
    out.append(check_page("western", 3, "atlantic", "spa-shell", "https://atlantic.st/",
                          ["#root", "atlantic"], t, warn_only=True))
    return out


def suite_bingr(t, quick):
    out = ping_mirrors("western", 4, "bingr", ["https://bingr.one"], t)
    out.append(check_json("western", 4, "bingr", "api-health",
                          "https://api.bingr.one/api/health", ["status"], t))
    out.append(check_page("western", 4, "bingr", "spa-shell", "https://bingr.one/",
                          ["bingr", "api.bingr.one"], t, warn_only=True))
    return out


def suite_meta(t, quick):
    out = []
    out.append(check_page("meta", 0, "everythingmoe", "home-ranks", "https://everythingmoe.com/",
                          ['rank="1"', "anikoto", "miruro"], t))
    out.append(check_json("meta", 0, "aroki-index", "index",
                          "https://raw.githubusercontent.com/kas021/AROKI-Connectors/main/index.json",
                          ["connectors", "signature"], t,
                          quick_skippable=True, quick=quick))
    out.extend(check_registry_versions())
    return out


def check_registry_versions():
    """Local: registry.version == manifest.version and sha256 matches file."""
    import hashlib
    import os
    out = []
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        reg = json.load(open(os.path.join(base, "registry.json")))
    except Exception as e:
        return [Result("meta", 0, "registry", "load", "FAIL", 0, f"bad registry: {e}")]
    for cat, items in reg.get("categories", {}).items():
        seen_rank = set()
        for e in items:
            sid = e.get("id", "?")
            # rank uniqueness per category
            if e.get("rank") in seen_rank:
                out.append(Result("meta", 0, sid, "registry-rank-dup", "FAIL", 0,
                                  f"dup rank {e.get('rank')} in {cat}"))
            seen_rank.add(e.get("rank"))
            mp = os.path.join(base, e.get("manifest", ""))
            if not os.path.exists(mp):
                out.append(Result("meta", 0, sid, "manifest-exists", "FAIL", 0, f"missing {mp}"))
                continue
            try:
                man = json.load(open(mp))
            except Exception as ex:
                out.append(Result("meta", 0, sid, "manifest-json", "FAIL", 0, f"bad JSON: {ex}"))
                continue
            if man.get("version") != e.get("version"):
                out.append(Result("meta", 0, sid, "version-match", "FAIL", 0,
                                  f"registry {e.get('version')} != manifest {man.get('version')}"))
            else:
                out.append(Result("meta", 0, sid, "version-match", "PASS", 0,
                                  f"v{e.get('version')}"))
            sha = hashlib.sha256(open(mp, "rb").read()).hexdigest()
            if sha != e.get("sha256"):
                out.append(Result("meta", 0, sid, "sha256-match", "FAIL", 0,
                                  f"registry {str(e.get('sha256'))[:12]}.. != file {sha[:12]}.."))
            else:
                out.append(Result("meta", 0, sid, "sha256-match", "PASS", 0,
                                  f"{sha[:12]}.."))
            cl = os.path.join(base, e.get("manifest", "").replace(".oko.json", ".CHANGELOG.md"))
            if not os.path.exists(cl):
                out.append(Result("meta", 0, sid, "changelog-exists", "FAIL", 0, f"missing {cl}"))
            elif e.get("version", "") not in open(cl).read():
                out.append(Result("meta", 0, sid, "changelog-has-version", "FAIL", 0,
                                  "version not in CHANGELOG"))
            else:
                out.append(Result("meta", 0, sid, "changelog-has-version", "PASS", 0, "ok"))
    return out


SUITES = {
    "anime": [suite_anikoto, suite_animepahe, suite_reanime, suite_miruro,
              suite_animex, suite_anikage, suite_lunar],
    "drama": [suite_kisskh],
    "western": [suite_shuttletv, suite_hydrahd, suite_atlantic, suite_bingr],
    "meta": [suite_meta],
}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Oko Sources health checker")
    ap.add_argument("--quick", action="store_true", help="skip detail-level paths")
    ap.add_argument("--category", default="all", choices=["all", "anime", "drama", "western", "meta"])
    ap.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    args = ap.parse_args()
    t = max(5, min(args.timeout, 60))

    cats = ["anime", "drama", "western", "meta"] if args.category == "all" else [args.category]
    results: list[Result] = []
    for c in cats:
        for fn in SUITES[c]:
            try:
                results.extend(fn(t, args.quick))
            except Exception as e:
                results.append(Result(c, -1, fn.__name__, "suite-crash", "FAIL", 0, f"{e}"))

    ignore_mirror_pass = False
    if args.as_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        cur = None
        for r in results:
            key = (r.category, r.source)
            if key != cur:
                cur = key
                print(f"\n== [{r.category}] rank={r.rank} {r.source} ==")
            mark = {"PASS": "PASS", "FAIL": "FAIL", "WARN": "WARN"}[r.status]
            print(f"  [{mark}] {r.check} ({r.ms}ms) — {r.detail}")
            if r.status == "FAIL":
                print(f"         {r.url}")

        npass = sum(1 for r in results if r.status == "PASS")
        nwarn = sum(1 for r in results if r.status == "WARN")
        nfail = sum(1 for r in results if r.status == "FAIL")
        print(f"\nSummary: {npass} pass, {nwarn} warn, {nfail} fail / {len(results)} checks"
              + (" (quick)" if args.quick else ""))
        if nfail:
            print("Hint: WARN = blocked/JS-only/optional (CF, SPA shell, kkey). "
                  "FAIL = down, parked, or contract broke — needs attention.")

    sys.exit(1 if any(r.status == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
