#!/usr/bin/env python3
"""
Build a browsable catalog from the Google-Playstore-Dataset (gauthamp10), for
Vyxel Apps / Appstore + the D-Store web storefront.

The upstream CSVs (dataset/Part{1,2,3}.csv) have 24 columns and NO icon URL, so
each row gets a deterministic generated tile (icon_color + icon_letter) instead of
a downloaded icon. Output is shaped like D-Store's `/api/catalog` rows so both
clients can read it with the parser they already have.

Usage:  python3 build_play_catalog.py <csv-dir> <out-dir> [min_installs] [cap_per_category]
"""
import csv, json, os, sys, glob, hashlib, datetime

H = ["App Name","App Id","Category","Rating","Rating Count","Installs","Minimum Installs",
     "Maximum Installs","Free","Price","Currency","Size","Minimum Android","Developer Id",
     "Developer Website","Developer Email","Released","Last Updated","Content Rating",
     "Privacy Policy","Ad Supported","In App Purchases","Editors Choice","Scraped Time"]

GAME_CATEGORIES = {
    "Action","Adventure","Arcade","Board","Card","Casual","Casino","Educational",
    "Music","Puzzle","Racing","Role Playing","Simulation","Sports","Strategy","Trivia","Word",
}

# A stable, distinguishable hue per category, so the generated tiles read as a set.
def category_color(cat: str) -> str:
    h = int(hashlib.sha1(cat.encode()).hexdigest(), 16)
    hue = h % 360
    return hsl_to_hex(hue, 0.62, 0.46)

def hsl_to_hex(h, s, l):
    c = (1 - abs(2*l - 1)) * s
    x = c * (1 - abs((h/60) % 2 - 1))
    m = l - c/2
    r, g, b = [(c,x,0),(x,c,0),(0,c,x),(0,x,c),(x,0,c),(c,0,x)][int(h//60) % 6]
    return "#%02x%02x%02x" % (int((r+m)*255), int((g+m)*255), int((b+m)*255))

def slugify(name: str) -> str:
    return name.strip().lower().replace(" ", "-")

def parse_size_mb(size: str) -> float:
    s = (size or "").strip()
    if not s or s == "Varies with device":
        return 0.0
    mult = {"k": 0.001, "m": 1.0, "g": 1024.0}
    if s[-1].lower() in mult:
        try: return round(float(s[:-1]) * mult[s[-1].lower()], 3)
        except: return 0.0
    try: return round(float(s) / (1024*1024), 3)
    except: return 0.0

def parse_int(s):
    try: return int(s)
    except: return 0

def norm_date(s: str) -> str:
    for fmt in ("%b %d, %Y", "%Y-%m-%d %H:%M:%S"):
        try: return datetime.datetime.strptime((s or "").strip(), fmt).strftime("%Y-%m-%d")
        except: pass
    return ""

def main():
    csv_dir = sys.argv[1]
    out_dir = sys.argv[2]
    min_installs = int(sys.argv[3]) if len(sys.argv) > 3 else 50000
    cap = int(sys.argv[4]) if len(sys.argv) > 4 else 2000

    shards = {}          # category -> list of app dicts
    seen = set()
    total = 0
    for fn in sorted(glob.glob(os.path.join(csv_dir, "Part*.csv"))):
        with open(fn, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f, fieldnames=H):
                pkg = (row["App Id"] or "").strip()
                if not pkg or pkg in seen:
                    continue
                inst = parse_int(row["Minimum Installs"])
                if inst < min_installs:
                    continue
                cat = (row["Category"] or "Other").strip() or "Other"
                name = (row["App Name"] or pkg).strip()
                seen.add(pkg)
                total += 1
                app = {
                    "origin": "play",
                    "package_name": pkg,
                    "slug": pkg,
                    "name": name,
                    "version": "",
                    "icon": "",
                    "icon_color": category_color(cat),
                    "icon_letter": (name[:1] or "?").upper(),
                    "summary": "",
                    "app_type": "game" if cat in GAME_CATEGORIES else "app",
                    "category": cat,
                    "developer": {"slug": slugify(row["Developer Id"] or name), "name": (row["Developer Id"] or "").strip()},
                    "license": "",
                    "size_mb": parse_size_mb(row["Size"]),
                    "download_url": None,
                    "reported_downloads": inst,
                    "rating": float(row["Rating"] or 0) if (row["Rating"] or "").strip() else 0.0,
                    "content_rating": (row["Content Rating"] or "").strip(),
                    "updated_at": norm_date(row["Last Updated"]),
                }
                shards.setdefault(cat, []).append(app)

    os.makedirs(os.path.join(out_dir, "apps"), exist_ok=True)
    categories = []
    all_apps = []
    for cat, apps in sorted(shards.items()):
        apps.sort(key=lambda a: a["reported_downloads"], reverse=True)
        kept = apps[:cap]
        all_apps.extend(kept)
        cslug = slugify(cat)
        with open(os.path.join(out_dir, "apps", cslug + ".json"), "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, separators=(",", ":"))
        categories.append({
            "slug": cslug, "name": cat,
            "app_type": "game" if cat in GAME_CATEGORIES else "app",
            "count": len(kept), "total_available": len(apps),
        })

    all_apps.sort(key=lambda a: a["reported_downloads"], reverse=True)
    with open(os.path.join(out_dir, "top.json"), "w", encoding="utf-8") as f:
        json.dump(all_apps[:1000], f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "categories.json"), "w", encoding="utf-8") as f:
        json.dump(categories, f, ensure_ascii=False, indent=1)
    manifest = {
        "schema_version": 1,
        "source": "gauthamp10/Google-Playstore-Dataset (MIT), scraped 2021-06",
        "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "min_installs": min_installs,
        "cap_per_category": cap,
        "total_apps": len(all_apps),
        "categories": len(categories),
        "shards": [c["slug"] for c in categories],
        "note": "No icon URL exists in the source; icon_color/icon_letter drive a generated tile. download_url is null: browse-only, never installable.",
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps(manifest, indent=1))

if __name__ == "__main__":
    main()
