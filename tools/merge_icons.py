#!/usr/bin/env python3
"""Merge scraped Play icons into the generated catalog shards."""
import glob, json, os, sys

catalog_dir, icons_path = sys.argv[1], sys.argv[2]
icons = json.load(open(icons_path, encoding="utf-8"))
merged = 0
for fn in sorted(glob.glob(os.path.join(catalog_dir, "apps", "*.json"))):
    apps = json.load(open(fn, encoding="utf-8"))
    changed = False
    for a in apps:
        hit = icons.get(a.get("package_name"))
        if hit and hit.get("icon", "").startswith("https://"):
            a["icon"] = hit["icon"]
            if hit.get("developer") and not a["developer"]["name"]:
                a["developer"]["name"] = hit["developer"]
            merged += 1
            changed = True
    if changed:
        json.dump(apps, open(fn, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
# top.json
tp = os.path.join(catalog_dir, "top.json")
top = json.load(open(tp, encoding="utf-8"))
for a in top:
    hit = icons.get(a.get("package_name"))
    if hit and hit.get("icon", "").startswith("https://"):
        a["icon"] = hit["icon"]
json.dump(top, open(tp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
# manifest
mp = os.path.join(catalog_dir, "manifest.json")
m = json.load(open(mp, encoding="utf-8"))
m["icons_resolved"] = merged
m["icons_source"] = "google-play-scraper (play-lh.googleusercontent.com)"
json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"merged {merged} icons into shards")
