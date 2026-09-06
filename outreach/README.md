# Colorado no-website outreach pipeline

Finds active Colorado businesses that appear to have no website, builds each one a complete
preview site, audits every page, and (after three pilot deals and owner sign-off) runs a
capped, CAN-SPAM-compliant email sequence pointing owners at their preview.

Read `GAME-PLAN.md` first. `COMPLIANCE.md` is the rulebook the sending agent must obey.

```
outreach/
  GAME-PLAN.md            phases, gates, pricing, what runs where
  COMPLIANCE.md           CAN-SPAM, Colorado law, domain/trademark rules, takedown SLA
  config/studio.json      who we are, pricing, send caps  <- set postal_address first
  config/industries.json  17 industries: name matchers, copy, FAQ, palette, fonts
  scripts/
    fetch_co_businesses.py  1. Colorado SOS open data -> leads/01_co_entities.csv
    enrich_leads.py         2. website check + phone/reviews/email -> leads/02_enriched.csv
    score_leads.py          3. rank, tier A/B/C -> leads/03_scored.csv + build_queue.json
    build_site.py           4. preview sites -> ../sites/<slug>/  (+ preview.html one-file)
    audit_site.py           5. auditor for sites + email templates -> reports/
    run_pipeline.sh         1..5 in order
  emails/                 3-touch sequence + reply templates (audited)
  leads/                  CSVs; sample-leads.csv drives the 3 demo sites
  reports/                audit-latest.md / .json
sites/                    generated previews (served by GitHub Pages at /sites/<slug>/)
```

## Quick start (office Mac or any machine with normal internet)

```bash
cd ~/lindaai-brain && git pull
pip3 install requests
export GOOGLE_MAPS_API_KEY=...          # optional but strongly recommended (best no-website signal)
bash outreach/scripts/run_pipeline.sh --since 2023-01-01 --enrich-limit 300 --top 25
open sites/index.html
```

Without the Places key the enrichment falls back to DuckDuckGo + domain guessing and marks
leads `probably-no` instead of `no`; they score lower and the emails say "couldn't find".

## Demo sites

`leads/sample-leads.csv` holds three fictional businesses. `build_site.py --csv leads/sample-leads.csv --single-file`
regenerates `sites/front-range-rooter-plumbing-arvada`, `sites/mile-high-lawn-snow-aurora`,
`sites/pikes-peak-mobile-detailing-colorado-springs`. Each has 9 pages plus a one-file
`preview.html`, all audited clean.

## Network note for cloud Claude sessions

The cloud sandbox's egress policy blocks data.colorado.gov, Google, DuckDuckGo, registrars and
hosting APIs (verified 2026-09-06: 403 at the proxy). Steps 1–3 must run on the office machine or in
a cloud environment whose network allowlist includes those hosts. Steps 4–5 run anywhere.
