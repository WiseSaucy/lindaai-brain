#!/usr/bin/env python3
"""Step 2 — figure out which businesses have NO website, and find a way to reach them.

For each candidate from step 1 this script records:
  has_website   yes | no | unknown   (+ website_url and the evidence used)
  phone, rating, review_count, business_status   (Google Places, when a key is set)
  facebook_url, email_candidates                  (best-effort discovery)

Providers, in order of trust:
  1. Google Places API (New)  — set GOOGLE_MAPS_API_KEY. The `websiteUri` field is the
     single best "does this business have a site" signal, and it returns the phone.
     Cost is roughly $0.03 per lookup; 2,000 lookups ≈ $60.
  2. DuckDuckGo HTML search    — free, no key. Looks for a result whose domain matches
     the business name, and captures a Facebook page URL if one shows up.
  3. Domain guessing           — tries <slug>.com/.net/.co etc., resolves DNS, fetches,
     and checks the page actually names the business.

A business is "no" only when Places returned a match without a website AND no
name-matching domain was found. Anything ambiguous stays "unknown" — we never want to
email someone "you don't have a website" when they do.

Usage:
  python3 scripts/enrich_leads.py --in leads/01_co_entities.csv --limit 500
Resumable: rows already present in the output file are skipped.
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import socket
import sys
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

import requests

from common import LEADS, read_csv, slugify, write_csv

UA = {"User-Agent": "Mozilla/5.0 (compatible; LindaAI-LeadCheck/1.0; +https://lindaai-brain.com)"}
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
SKIP_DOMAINS = (
    "facebook.com", "yelp.com", "google.com", "bbb.org", "yellowpages.com", "mapquest.com",
    "linkedin.com", "instagram.com", "nextdoor.com", "angi.com", "homeadvisor.com", "thumbtack.com",
    "bizapedia.com", "opencorporates.com", "manta.com", "dnb.com", "buzzfile.com", "zoominfo.com",
    "sos.state.co.us", "coloradosos.gov", "data.colorado.gov", "chamberofcommerce.com", "cortera.com",
    "porch.com", "houzz.com", "alignable.com", "birdeye.com", "tiktok.com", "youtube.com", "x.com",
    "twitter.com", "indeed.com", "glassdoor.com", "apple.com", "wikipedia.org", "duckduckgo.com",
)


def name_tokens(name: str) -> list[str]:
    stop = {"the", "and", "of", "co", "llc", "inc", "services", "service", "company", "colorado", "denver"}
    return [t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in stop and len(t) > 2]


def domain_matches_name(domain: str, name: str) -> bool:
    d = domain.lower().split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    if any(d.endswith(s) for s in SKIP_DOMAINS):
        return False
    core = d.split(".")[0]
    toks = name_tokens(name)
    if not toks:
        return False
    joined = "".join(toks)
    hits = sum(1 for t in toks if t in core)
    return core in joined or hits >= max(1, min(2, len(toks)))


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


# ---------------------------------------------------------------- Google Places (New)
def places_lookup(name: str, city: str, key: str) -> dict | None:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": ",".join([
            "places.id", "places.displayName", "places.websiteUri", "places.nationalPhoneNumber",
            "places.rating", "places.userRatingCount", "places.formattedAddress", "places.businessStatus",
        ]),
    }
    body = {"textQuery": f"{name} {city} Colorado", "maxResultCount": 5, "regionCode": "US"}
    r = requests.post(url, json=body, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"    places {r.status_code}: {r.text[:120]}", file=sys.stderr)
        return None
    best, best_score = None, 0.0
    for p in r.json().get("places", []):
        disp = p.get("displayName", {}).get("text", "")
        score = difflib.SequenceMatcher(None, disp.lower(), name.lower()).ratio()
        addr = p.get("formattedAddress", "")
        if city.lower() in addr.lower():
            score += 0.1
        if score > best_score:
            best, best_score = p, score
    if best and best_score >= 0.62:
        return {
            "google_place_id": best.get("id", ""),
            "google_name": best.get("displayName", {}).get("text", ""),
            "google_match_score": round(best_score, 2),
            "website_url": best.get("websiteUri", "") or "",
            "phone": best.get("nationalPhoneNumber", "") or "",
            "rating": best.get("rating", ""),
            "review_count": best.get("userRatingCount", ""),
            "business_status": best.get("businessStatus", ""),
            "google_address": best.get("formattedAddress", ""),
        }
    return {"google_place_id": "", "google_match_score": round(best_score, 2)}


# ---------------------------------------------------------------- DuckDuckGo
def ddg_search(query: str) -> list[str]:
    r = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=UA, timeout=30)
    if r.status_code != 200:
        return []
    p = LinkParser()
    p.feed(r.text)
    urls = []
    for href in p.links:
        if "uddg=" in href:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = q.get("uddg", [""])[0]
        if href.startswith("http"):
            urls.append(href)
    return urls


# ---------------------------------------------------------------- domain guessing
def guess_domains(name: str, city: str) -> list[str]:
    toks = name_tokens(name)
    if not toks:
        return []
    base = "".join(toks)
    dashed = "-".join(toks)
    cslug = slugify(city).replace("-", "")
    cands = [base, dashed, base + cslug, base + "co", base + "colorado", base + "llc"]
    out = []
    for c in cands:
        for tld in (".com", ".net", ".co", ".biz", ".us"):
            out.append(c + tld)
    return out[:18]


def probe(domain: str, name: str) -> tuple[bool, str, list[str]]:
    try:
        socket.gethostbyname(domain)
    except OSError:
        return False, "", []
    for scheme in ("https://", "http://"):
        try:
            r = requests.get(scheme + domain, headers=UA, timeout=12, allow_redirects=True)
        except requests.RequestException:
            continue
        if r.status_code >= 400:
            continue
        text = r.text[:200000]
        p = LinkParser()
        p.feed(text)
        toks = name_tokens(name)
        hay = (p.title + " " + text[:20000]).lower()
        hits = sum(1 for t in toks if t in hay)
        parked = any(k in hay for k in ("domain is for sale", "parked", "godaddy.com/domains", "buy this domain", "sedo"))
        if hits >= max(1, min(2, len(toks))) and not parked:
            return True, r.url, EMAIL_RE.findall(text)[:5]
    return False, "", []


def enrich_row(row: dict, key: str | None, use_ddg: bool, use_guess: bool) -> dict:
    name, city = row["name"], row.get("city", "")
    ev = []
    website = ""
    if key:
        g = places_lookup(name, city, key)
        if g:
            row.update({k: v for k, v in g.items() if k != "website_url"})
            if g.get("website_url"):
                website = g["website_url"]
                ev.append("places:websiteUri")
            elif g.get("google_place_id"):
                ev.append("places:matched-no-website")
            else:
                ev.append("places:no-match")
        time.sleep(0.2)
    fb = ""
    emails: list[str] = []
    if not website and use_ddg:
        for u in ddg_search(f'"{name}" {city} CO')[:10]:
            host = urllib.parse.urlparse(u).netloc
            if "facebook.com" in host and not fb:
                fb = u
            elif domain_matches_name(host, name):
                website = u
                ev.append(f"ddg:{host}")
                break
        time.sleep(1.5)
    if not website and use_guess:
        for d in guess_domains(name, city):
            ok, url, em = probe(d, name)
            if ok:
                website, emails = url, em
                ev.append(f"guess:{d}")
                break
    if website:
        has = "yes"
    elif "places:matched-no-website" in ev:
        has = "no"
    elif key and "places:no-match" in ev and not fb:
        has = "unknown"          # might not be an operating storefront at all
    elif not key and (use_ddg or use_guess):
        has = "probably-no"      # no key: weaker signal, still worth a touch
    else:
        has = "unknown"
    row.update({
        "has_website": has,
        "website_url": website,
        "website_evidence": ";".join(ev),
        "facebook_url": fb,
        "email_candidates": ";".join(dict.fromkeys(emails)),
    })
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="inp", default=str(LEADS / "01_co_entities.csv"))
    p.add_argument("--out", default=str(LEADS / "02_enriched.csv"))
    p.add_argument("--limit", type=int, default=300, help="rows to process this run")
    p.add_argument("--no-ddg", action="store_true")
    p.add_argument("--no-guess", action="store_true")
    args = p.parse_args()
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        print("GOOGLE_MAPS_API_KEY not set — falling back to DuckDuckGo + domain guessing (weaker signal).", file=sys.stderr)
    rows = read_csv(Path(args.inp))
    out_path = Path(args.out)
    done = {r["entity_id"] for r in read_csv(out_path)} if out_path.exists() else set()
    existing = read_csv(out_path) if out_path.exists() else []
    todo = [r for r in rows if r["entity_id"] not in done][: args.limit]
    print(f"{len(todo)} to enrich ({len(done)} already done)", file=sys.stderr)
    for i, row in enumerate(todo, 1):
        try:
            existing.append(enrich_row(row, key, not args.no_ddg, not args.no_guess))
        except requests.RequestException as e:
            row.update({"has_website": "unknown", "website_evidence": f"error:{e.__class__.__name__}"})
            existing.append(row)
        if i % 10 == 0 or i == len(todo):
            write_csv(out_path, existing)
            print(f"  {i}/{len(todo)}  last: {row['name']} -> {row.get('has_website')}", file=sys.stderr)
    write_csv(out_path, existing)
    tally = {}
    for r in existing:
        tally[r.get("has_website", "?")] = tally.get(r.get("has_website", "?"), 0) + 1
    print(f"done. has_website tally: {tally}", file=sys.stderr)


if __name__ == "__main__":
    main()
