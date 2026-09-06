#!/usr/bin/env bash
# End-to-end: SOS pull -> website check -> score -> build previews -> audit.
# Run from a machine with open network (office Mac) or a cloud environment whose
# allowlist includes data.colorado.gov, places.googleapis.com, html.duckduckgo.com.
#
#   GOOGLE_MAPS_API_KEY=... bash outreach/scripts/run_pipeline.sh [--since 2023-01-01] [--enrich-limit 300] [--top 25]
set -euo pipefail
cd "$(dirname "$0")"
SINCE=$(date -d '3 years ago' +%F 2>/dev/null || date -v-3y +%F)
ENRICH_LIMIT=300
TOP=25
while [[ $# -gt 0 ]]; do
  case "$1" in
    --since) SINCE="$2"; shift 2;;
    --enrich-limit) ENRICH_LIMIT="$2"; shift 2;;
    --top) TOP="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
echo "== 1/5 pull Colorado SOS entities (since $SINCE)"
python3 fetch_co_businesses.py --since "$SINCE"
echo "== 2/5 check website presence + contacts (limit $ENRICH_LIMIT this run)"
python3 enrich_leads.py --limit "$ENRICH_LIMIT"
echo "== 3/5 score + queue"
python3 score_leads.py --top "$TOP"
echo "== 4/5 build preview sites"
python3 build_site.py --queue ../leads/build_queue.json --single-file
echo "== 5/5 audit"
python3 audit_site.py   # add --send-ready before any live send
echo "done. leads -> outreach/leads/03_scored.csv   sites -> sites/   report -> outreach/reports/audit-latest.md"
