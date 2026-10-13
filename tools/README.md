# Play catalogue — tools

This repository is a fork of
[gauthamp10/Google-Playstore-Dataset](https://github.com/gauthamp10/Google-Playstore-Dataset)
that carries a **pre-derived, phone-sized** slice of it in [`catalog/`](../catalog):

- `manifest.json` — totals, schema version, provenance
- `categories.json` — the 48 Play categories and their row counts
- `top.json` — a cross-category top list
- `apps/<category>.json` — one shard per category, up to 2,000 apps each

The upstream repo ships three ~70 MB tarballs; this fork ships small JSON so a
phone fetches a few hundred KB instead of cloning 274 MB. Rows carry a real
`play-lh.googleusercontent.com` icon URL where one could be scraped, and a
deterministic `icon_color`/`icon_letter` for a generated tile otherwise.

## Scripts

| Script | Purpose |
| --- | --- |
| `build_play_catalog.py` | Derives `catalog/` from the three upstream CSVs (min installs, per-category cap). Run once; slow. |
| `scrape_icons.py` | One-off bulk icon scrape (resumable, concurrent). |
| `merge_icons.py` | Merges a scrape result into the shards. |
| `refresh_play_catalog.py` | **Resident.** Prunes delisted apps and fills icons, a bounded slice per run. Safe to run on a schedule. |

## `refresh_play_catalog.py`

Two jobs, both driven by the same Play lookup:

1. **Prune delisted apps.** The dataset was scraped in 2021; apps removed from
   Play since then return `NotFoundError` (404 on their Play page). They are
   dropped so the catalogue never offers an app that no longer exists. Only a
   definitive `NotFoundError` prunes — a transient network/5xx error leaves the
   row alone, so a bad night never deletes live apps.
2. **Fill icons.** Each row without an icon URL is looked up and its real icon
   stored. Resumable: a row that already has an icon is skipped.

```bash
pip install google-play-scraper
python tools/refresh_play_catalog.py --catalog-dir catalog --icon-budget 4000 --workers 8
```

Keep `--workers` low (6–8). At 32 workers Play rate-limits and the run reports
large numbers of `transient` lookups, which is misleading — many of those are
real delistings that only resolve at a gentler pace.

### Continuous refresh

[`.github/workflows/refresh-catalog.yml`](../.github/workflows/refresh-catalog.yml)
runs the script every 6 hours and commits any change, so the catalogue stays
icon-complete and delisting-free without a one-day manual effort. Manual runs
take a larger `icon_budget` via *Run workflow*.

## Provenance

Upstream data is MIT-licensed (see upstream `LICENSE`). Icons are fetched from
Google Play's public CDN for identification of the listed app.
