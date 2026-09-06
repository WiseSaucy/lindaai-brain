"""Shared helpers for the Colorado no-website outreach pipeline."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # outreach/
REPO = ROOT.parent                                   # repo root
CONFIG = ROOT / "config"
LEADS = ROOT / "leads"
REPORTS = ROOT / "reports"
SITES = REPO / "sites"

LEGAL_SUFFIX = re.compile(
    r"\b(l\.?l\.?c\.?|inc\.?|incorporated|corp\.?|corporation|co\.?|ltd\.?|limited|"
    r"l\.?l\.?p\.?|lp|pllc|pc|p\.c\.|dba|company)\b\.?",
    re.I,
)


def load_json(name: str) -> dict:
    return json.loads((CONFIG / name).read_text())


def studio() -> dict:
    return load_json("studio.json")


def industries() -> dict:
    return load_json("industries.json")


def clean_name(raw: str) -> str:
    """'FRONT RANGE ROOTER & PLUMBING LLC' -> 'Front Range Rooter & Plumbing'."""
    s = unicodedata.normalize("NFKC", raw or "").strip()
    s = re.sub(r",?\s*$", "", s)
    s = LEGAL_SUFFIX.sub("", s).strip(" ,.-")
    if s.isupper() or s.islower():
        s = smart_title(s)
    return re.sub(r"\s{2,}", " ", s)


def smart_title(s: str) -> str:
    small = {"and", "of", "the", "&", "a", "an", "in", "on", "at", "for", "to", "by"}
    words = []
    for i, w in enumerate(s.lower().split()):
        if w in small and i:
            words.append(w)
        elif re.match(r"^[a-z]&[a-z]$", w):
            words.append(w.upper())
        else:
            words.append(w[:1].upper() + w[1:])
    return " ".join(words)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "business"


def classify(name: str, lib: dict | None = None) -> str:
    """Return the industry key whose match regexes hit the name, else 'generic'."""
    lib = lib or industries()
    n = (name or "").lower()
    for key, ind in lib["industries"].items():
        for pat in ind.get("match", []):
            if re.search(pat, n):
                return key
    return "generic"


def excluded(name: str, lib: dict | None = None) -> str | None:
    lib = lib or industries()
    n = (name or "").lower()
    for pat in lib.get("exclude_match", []):
        if re.search(pat, n):
            return pat
    return None


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fieldnames = fieldnames or list({k: None for r in rows for k in r}.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "t"}
