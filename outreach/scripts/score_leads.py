#!/usr/bin/env python3
"""Step 3 — score and rank enriched leads, and write the build queue.

Score (0–100):
  no website          40   (probably-no 25, unknown 10, yes -> dropped)
  industry ticket     30 / 20 / 10  (high / mid / low job value, from industries.json)
  business age        10   between 6 months and 8 years old (new enough to care, old enough to be real)
  has reviews         10   Google review_count > 0 (a real, operating storefront)
  phone known          5
  target city          5
Tier A >= 75, B 55–74, C < 55.  Only A and B go into the build queue by default.

Usage:  python3 scripts/score_leads.py --top 50
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from common import LEADS, classify, industries, read_csv, slugify, write_csv


def score(row: dict, lib: dict) -> tuple[int, list[str]]:
    why = []
    s = 0
    hw = row.get("has_website", "unknown")
    if hw == "yes":
        return -1, ["has a website"]
    s += {"no": 40, "probably-no": 25}.get(hw, 10)
    why.append(f"website:{hw}")
    ind = row.get("industry") or classify(row.get("name", ""), lib)
    row["industry"] = ind
    ticket = lib["industries"].get(ind, {}).get("ticket", 1)
    s += {3: 30, 2: 20}.get(ticket, 10)
    why.append(f"ticket:{ticket}")
    try:
        formed = dt.date.fromisoformat(row.get("form_date", "")[:10])
        age_days = (dt.date.today() - formed).days
        if 180 <= age_days <= 8 * 365:
            s += 10
            why.append("age-ok")
    except ValueError:
        pass
    try:
        if int(float(row.get("review_count") or 0)) > 0:
            s += 10
            why.append("has-reviews")
    except ValueError:
        pass
    if row.get("phone"):
        s += 5
        why.append("phone")
    if row.get("city", "").title() in lib["target_cities"]:
        s += 5
        why.append("target-city")
    if row.get("business_status") and row["business_status"] != "OPERATIONAL":
        s -= 30
        why.append("not-operational")
    return max(0, min(100, s)), why


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="inp", default=str(LEADS / "02_enriched.csv"))
    p.add_argument("--out", default=str(LEADS / "03_scored.csv"))
    p.add_argument("--queue", default=str(LEADS / "build_queue.json"))
    p.add_argument("--top", type=int, default=50, help="max leads in the build queue")
    p.add_argument("--min-tier", default="B", choices=["A", "B", "C"])
    args = p.parse_args()
    lib = industries()
    rows = read_csv(Path(args.inp))
    kept = []
    for r in rows:
        s, why = score(r, lib)
        if s < 0:
            continue
        r["score"] = s
        r["tier"] = "A" if s >= 75 else "B" if s >= 55 else "C"
        r["why"] = ",".join(why)
        r["slug"] = slugify(f"{r['name']}-{r.get('city', '')}")
        kept.append(r)
    kept.sort(key=lambda r: (-int(r["score"]), r["name"]))
    write_csv(Path(args.out), kept)
    allowed = {"A": ["A"], "B": ["A", "B"], "C": ["A", "B", "C"]}[args.min_tier]
    queue = [r for r in kept if r["tier"] in allowed][: args.top]
    Path(args.queue).write_text(json.dumps(queue, indent=2))
    tiers = {t: sum(1 for r in kept if r["tier"] == t) for t in "ABC"}
    print(f"scored {len(kept)} leads  tiers {tiers}  queue {len(queue)} -> {args.queue}", file=sys.stderr)


if __name__ == "__main__":
    main()
