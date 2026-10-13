#!/usr/bin/env python3
"""
Scrape real Google Play icons for the catalog built from gauthamp10/Google-Playstore-Dataset.

The upstream dataset has no icon URL, so we resolve one per package_name straight from
Play. Resumable: a package already in the output file (or the checkpoint) is skipped, so
a re-run only fetches what is missing. Bounded: --per-category keeps the run to the apps
that actually reach the home shelves/carousel.

Usage:
  python3 scrape_icons.py --catalog-dir out --out icons.json --per-category 200 --workers 16
"""
import argparse, glob, json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from google_play_scraper import app as gp_app
except ImportError:
    sys.exit("pip install google-play-scraper")

lock = threading.Lock()


def load_done(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def targets(catalog_dir, per_category, offset):
    """Package names to scrape: the top `per_category` per category shard, by downloads."""
    pkgs = []
    for fn in sorted(glob.glob(os.path.join(catalog_dir, "apps", "*.json"))):
        try:
            apps = json.load(open(fn, encoding="utf-8"))
        except Exception:
            continue
        apps.sort(key=lambda a: a.get("reported_downloads") or 0, reverse=True)
        for a in apps[offset:offset + per_category]:
            pkg = a.get("package_name")
            if pkg:
                pkgs.append(pkg)
    return pkgs


def fetch(pkg):
    try:
        d = gp_app(pkg, lang="en", country="us")
        icon = d.get("icon") or ""
        if not icon.startswith("https://"):
            return pkg, None
        return pkg, {
            "icon": icon,
            "title": d.get("title") or "",
            "developer": d.get("developer") or "",
            "score": d.get("score") or 0,
            "installs": d.get("installs") or "",
            "genre": d.get("genre") or "",
        }
    except Exception:
        return pkg, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog-dir", default="out")
    ap.add_argument("--out", default="icons.json")
    ap.add_argument("--per-category", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    done = load_done(args.out)
    pkgs = targets(args.catalog_dir, args.per_category, args.offset)
    todo = [p for p in pkgs if p not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"targets={len(pkgs)} already={len(done)} todo={len(todo)}", flush=True)

    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch, p): p for p in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            pkg, res = fut.result()
            with lock:
                if res:
                    done[pkg] = res
                    ok += 1
            if i % 100 == 0:
                with lock:
                    json.dump(done, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
                print(f"  {i}/{len(todo)} done, {ok} with icons", flush=True)

    with lock:
        json.dump(done, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"FINISHED: {ok}/{len(todo)} resolved; {len(done)} total in {args.out}", flush=True)


if __name__ == "__main__":
    main()
