#!/usr/bin/env python3
"""Step 1 — pull Colorado business entities from the Secretary of State open-data feed.

Source: Colorado Information Marketplace, dataset "Business Entities in Colorado"
        https://data.colorado.gov/resource/4ykn-tg5h.json  (Socrata SODA API)
The SOS feed has NO phone, email, or industry. It gives us: legal name, principal
address, formation date, status, and registered agent. Industry is inferred from the
name (config/industries.json); contact details come later from enrich_leads.py.

Usage:
  python3 scripts/fetch_co_businesses.py --since 2023-01-01 --max 150000
  SOCRATA_APP_TOKEN=... python3 scripts/fetch_co_businesses.py   # higher rate limit

Network: needs HTTPS to data.colorado.gov. Cloud Claude sessions with a locked network
policy will get a 403 from the proxy; run this from the office machine or an
environment whose allowlist includes data.colorado.gov.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import requests

from common import LEADS, classify, clean_name, excluded, industries, write_csv

BASE = "https://data.colorado.gov/resource/{dataset}.json"
DEFAULT_DATASET = "4ykn-tg5h"
FIELDS = [
    "entityid", "entityname", "entitytype", "entitystatus", "entityformdate",
    "principaladdress1", "principaladdress2", "principalcity", "principalstate",
    "principalzipcode", "agentfirstname", "agentlastname", "agentorganizationname",
]


def soql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def build_where(args, cities: list[str]) -> str:
    parts = [
        "entitystatus='Good Standing'",
        "principalstate='CO'",
        f"entityformdate >= '{args.since}T00:00:00.000'",
    ]
    if args.until:
        parts.append(f"entityformdate <= '{args.until}T23:59:59.000'")
    if cities:
        parts.append("upper(principalcity) in (" + ",".join(soql_quote(c.upper()) for c in cities) + ")")
    if args.entity_types:
        parts.append("entitytype in (" + ",".join(soql_quote(t) for t in args.entity_types) + ")")
    return " AND ".join(parts)


def fetch(args) -> list[dict]:
    lib = industries()
    cities = [] if args.all_cities else (args.cities or lib["target_cities"])
    where = build_where(args, cities)
    headers = {"Accept": "application/json"}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    url = BASE.format(dataset=args.dataset)
    out: list[dict] = []
    offset = 0
    page = 5000
    kept = dropped_excl = dropped_generic = 0
    while offset < args.max:
        params = {
            "$select": ",".join(FIELDS),
            "$where": where,
            "$order": "entityid",
            "$limit": min(page, args.max - offset),
            "$offset": offset,
        }
        for attempt in range(5):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=120)
                if r.status_code == 403:
                    sys.exit("403 from proxy/host: this environment cannot reach data.colorado.gov. "
                             "Run from the office machine or allowlist the domain in the cloud environment.")
                r.raise_for_status()
                break
            except requests.RequestException as e:  # noqa: PERF203
                wait = 2 ** attempt
                print(f"  retry {attempt + 1}/5 after error: {e} (sleep {wait}s)", file=sys.stderr)
                time.sleep(wait)
        else:
            sys.exit("giving up on the SOS feed after 5 attempts")
        rows = r.json()
        if not rows:
            break
        for row in rows:
            raw = row.get("entityname", "")
            if not args.keep_all:
                if excluded(raw, lib):
                    dropped_excl += 1
                    continue
                ind = classify(raw, lib)
                if ind == "generic" and not args.include_generic:
                    dropped_generic += 1
                    continue
            else:
                ind = classify(raw, lib)
            agent = " ".join(x for x in [row.get("agentfirstname"), row.get("agentlastname")] if x) or row.get("agentorganizationname", "")
            out.append({
                "entity_id": row.get("entityid", ""),
                "legal_name": raw,
                "name": clean_name(raw),
                "industry": ind,
                "entity_type": row.get("entitytype", ""),
                "status": row.get("entitystatus", ""),
                "form_date": (row.get("entityformdate") or "")[:10],
                "address1": row.get("principaladdress1", ""),
                "address2": row.get("principaladdress2", ""),
                "city": (row.get("principalcity") or "").title(),
                "state": row.get("principalstate", "CO"),
                "zip": (row.get("principalzipcode") or "")[:5],
                "agent": agent,
                "source": f"co-sos:{args.dataset}",
                "fetched": dt.date.today().isoformat(),
            })
            kept += 1
        offset += len(rows)
        print(f"  fetched {offset:>7} rows  kept {kept:>6}  excluded {dropped_excl:>6}  generic {dropped_generic:>6}", file=sys.stderr)
        if len(rows) < page:
            break
        time.sleep(0.3)
    return out


def main() -> None:
    three_years_ago = (dt.date.today() - dt.timedelta(days=3 * 365)).isoformat()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default=DEFAULT_DATASET, help="Socrata dataset id (default: business entities)")
    p.add_argument("--since", default=three_years_ago, help="formation date floor YYYY-MM-DD")
    p.add_argument("--until", default=None, help="formation date ceiling YYYY-MM-DD")
    p.add_argument("--cities", nargs="*", help="override target cities (default: config target_cities)")
    p.add_argument("--all-cities", action="store_true", help="no city filter (all of Colorado)")
    p.add_argument("--entity-types", nargs="*", default=None,
                   help="e.g. 'Limited Liability Company' 'Corporation' (default: all)")
    p.add_argument("--max", type=int, default=200000, help="max rows to pull from the API")
    p.add_argument("--include-generic", action="store_true", help="keep names that match no industry")
    p.add_argument("--keep-all", action="store_true", help="skip industry/exclusion filtering entirely")
    p.add_argument("--out", default=str(LEADS / "01_co_entities.csv"))
    args = p.parse_args()

    print(f"Pulling CO SOS entities formed since {args.since} …", file=sys.stderr)
    rows = fetch(args)
    write_csv(Path(args.out), rows)
    print(f"wrote {len(rows)} candidate businesses -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
