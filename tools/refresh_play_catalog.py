#!/usr/bin/env python3
"""
Keep the generated Play catalogue honest and icon-complete, a bounded slice per run.

Two jobs, both driven by the same Play lookup:

  1. Prune delisted apps. The source dataset was scraped in 2021; apps removed from
     Play since then return `NotFoundError` (and a 404 on their Play page). They are
     dropped from the shards so the catalogue never offers an app that no longer
     exists. Only a definitive `NotFoundError` prunes — a transient network or 5xx
     error leaves the row alone, so a bad night never deletes live apps.

  2. Fill icons. The dataset ships no icon URL, so each row without one is looked up
     and its real `play-lh.googleusercontent.com` icon stored. Bounded by
     `--icon-budget` per run: this is meant to be run on a schedule (see
     `.github/workflows/refresh-catalog.yml`), not to resolve 84,000 apps in one
     sitting. Every run is resumable — a row that already has an icon is skipped.

Usage:
  python3 refresh_play_catalog.py --catalog-dir catalog --icon-budget 4000 --workers 24
"""
import argparse, glob, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from google_play_scraper import app as gp_app
    from google_play_scraper.exceptions import NotFoundError
except ImportError:
    sys.exit("pip install google-play-scraper")

FOUND, DELISTED, TRANSIENT = "found", "delisted", "transient"
lock = threading.Lock()


def lookup(pkg):
    """One Play lookup, classified so the caller can act safely on the result."""
    try:
        d = gp_app(pkg, lang="en", country="us")
    except NotFoundError:
        return pkg, DELISTED, None
    except Exception:
        return pkg, TRANSIENT, None
    icon = d.get("icon") or ""
    if not icon.startswith("https://"):
        return pkg, TRANSIENT, None
    return pkg, FOUND, {
        "icon": icon,
        "developer": d.get("developer") or "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog-dir", default="catalog")
    ap.add_argument("--icon-budget", type=int, default=4000, help="max Play lookups this run")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--prune/--no-prune", dest="prune", default=True)
    args = ap.parse_args()

    shards = {}
    for fn in sorted(glob.glob(os.path.join(args.catalog_dir, "apps", "*.json"))):
        shards[fn] = json.load(open(fn, encoding="utf-8"))

    # Rows that still need a lookup: no icon yet. Icons first — a resolved icon is
    # the visible win; a delisting is a correctness fix and both come from one call.
    todo = []
    for fn, apps in shards.items():
        for a in apps:
            if not (a.get("icon") or "").startswith("https://"):
                todo.append((fn, a.get("package_name") or ""))
    todo = [(fn, p) for fn, p in todo if p][: args.icon_budget]
    print(f"shards={len(shards)} rows_needing_lookup={len(todo)} (budget {args.icon_budget})", flush=True)

    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(lookup, p): (fn, p) for fn, p in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            pkg, status, data = fut.result()
            with lock:
                results[pkg] = (status, data)
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}", flush=True)

    found = sum(1 for s, _ in results.values() if s == FOUND)
    delisted = [p for p, (s, _) in results.items() if s == DELISTED]
    transient = sum(1 for s, _ in results.values() if s == TRANSIENT)
    print(f"lookups={len(results)} found={found} delisted={len(delisted)} transient={transient}", flush=True)

    pruned = 0
    for fn, apps in shards.items():
        kept = []
        for a in apps:
            pkg = a.get("package_name") or ""
            status, data = results.get(pkg, (None, None))
            if status == DELISTED and args.prune:
                pruned += 1
                continue
            if status == FOUND and data:
                a["icon"] = data["icon"]
                if data.get("developer") and not (a.get("developer") or {}).get("name"):
                    a.setdefault("developer", {})["name"] = data["developer"]
            kept.append(a)
        shards[fn] = kept
        json.dump(kept, open(fn, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # Keep top.json consistent with the pruned shards.
    tp = os.path.join(args.catalog_dir, "top.json")
    if os.path.exists(tp):
        top = json.load(open(tp, encoding="utf-8"))
        top = [a for a in top if (a.get("package_name") or "") not in set(delisted)]
        for a in top:
            status, data = results.get(a.get("package_name") or "", (None, None))
            if status == FOUND and data:
                a["icon"] = data["icon"]
        json.dump(top, open(tp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    total = sum(len(v) for v in shards.values())

    # Category counts move as rows are pruned, so keep categories.json in step.
    cp = os.path.join(args.catalog_dir, "categories.json")
    if os.path.exists(cp):
        cats = json.load(open(cp, encoding="utf-8"))
        for c in cats:
            fn = os.path.join(args.catalog_dir, "apps", c["slug"] + ".json")
            if fn in shards:
                c["count"] = len(shards[fn])
        json.dump(cats, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    mp = os.path.join(args.catalog_dir, "manifest.json")
    if os.path.exists(mp):
        m = json.load(open(mp, encoding="utf-8"))
        m["total_apps"] = total
        m["icons_resolved"] = sum(
            1 for apps in shards.values() for a in apps if (a.get("icon") or "").startswith("https://")
        )
        m["pruned_delisted"] = m.get("pruned_delisted", 0) + pruned
        m["icons_source"] = "google-play-scraper (play-lh.googleusercontent.com)"
        json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"applied: icons+={found} pruned={pruned} total_apps={total}", flush=True)


if __name__ == "__main__":
    main()
