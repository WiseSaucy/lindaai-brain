#!/usr/bin/env python3
"""Step 5 — website auditor. Run before any preview is sent and again before handoff.

Checks every generated site (sites/<slug>/*.html) for:
  structure     doctype, lang, charset, viewport, <title> length, meta description length,
                exactly one <h1>, heading order, skip link, <main>, landmarks
  required      FAQ, privacy, terms, accessibility, contact pages exist and are linked
                from every page's footer; contact page has a tel: link
  preview mode  preview banner present + robots noindex on every page (meta lindaai-mode)
  content       no lorem/TODO/{{placeholders}}/POSTAL_ADDRESS, no unverified credential
                claims (licensed, insured, certified, award, #1, years of experience,
                guarantee, 5-star), no fabricated testimonials or star ratings
  links         every internal href/src resolves to a file; external links that open a
                new tab carry rel=noopener
  hygiene       no inline event handlers, no external scripts, images have alt, page < 300 KB
Also audits outreach/emails/*.md for CAN-SPAM essentials.

Usage
  python3 scripts/audit_site.py                    # all sites + email templates
  python3 scripts/audit_site.py sites/some-slug    # one site
  python3 scripts/audit_site.py --strict           # WARN counts as failure
Exit code 1 when any FAIL (or WARN with --strict). Reports -> outreach/reports/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from common import REPO, REPORTS, ROOT, SITES

REQUIRED_PAGES = ["index.html", "faq.html", "privacy.html", "terms.html", "accessibility.html", "contact.html", "services.html", "about.html"]
FOOTER_LINKS = ["faq.html", "privacy.html", "terms.html", "accessibility.html", "contact.html"]
PLACEHOLDER = re.compile(r"lorem ipsum|\bTODO\b|\bTBD\b|\{\{[^}]*\}\}|POSTAL_ADDRESS|\[INSERT|\[YOUR |XXX-XXX", re.I)
CLAIMS = re.compile(
    r"\b(licensed|insured|bonded|certified|award[- ]winning|#1|number one|best in|top[- ]rated|"
    r"\d+\+? years (of )?experience|years in business|guarantee[ds]?|5[- ]star|five[- ]star|bbb accredited|family[- ]owned|veteran[- ]owned)\b",
    re.I,
)
TESTIMONIAL = re.compile(r"testimonial|★|⭐|what (our )?(customers|clients) say|reviews?:", re.I)
SEND_READY = False  # set by --send-ready: everything a live send needs must be in place
ALLOWED_VARS = {"name", "first_name", "city", "preview_url", "industry", "phone", "studio_name", "offer_name", "from_name",
                "postal_address", "contact_email", "website", "unsubscribe_note", "claim_url", "date", "owner_name",
                "setup_fee", "monthly_care", "one_time_transfer"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.h: list[str] = []
        self.links: list[tuple[str, dict]] = []
        self.srcs: list[str] = []
        self.imgs_without_alt = 0
        self.inline_handlers = 0
        self.external_scripts: list[str] = []
        self.has_main = self.has_header = self.has_footer = self.has_nav = False
        self.skip_link = False
        self.lang = ""
        self.charset = False
        self.text_parts: list[str] = []
        self.in_footer = False
        self.footer_links: list[str] = []
        self.in_title = False
        self.forms: list[dict] = []
        self.banner = False
        self.tag_stack: list[str] = []
        self.unclosed = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if any(k.startswith("on") for k in a):
            self.inline_handlers += 1
        if tag == "html":
            self.lang = a.get("lang", "")
        if tag == "meta":
            if "charset" in a:
                self.charset = True
            if a.get("name"):
                self.meta[a["name"].lower()] = a.get("content", "")
        if tag == "title":
            self.in_title = True
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.h.append(tag)
        if tag == "a":
            href = a.get("href", "")
            self.links.append((href, a))
            if self.in_footer:
                self.footer_links.append(href)
            if href.startswith("#main") and "skip" in (a.get("class") or ""):
                self.skip_link = True
        if tag in ("img", "source", "iframe"):
            if a.get("src"):
                self.srcs.append(a["src"])
        if tag == "link" and a.get("rel") == "stylesheet" and a.get("href", "").startswith(("styles", "./")):
            self.srcs.append(a["href"])
        if tag == "img" and not a.get("alt") and a.get("alt") != "":
            self.imgs_without_alt += 1
        if tag == "script" and a.get("src"):
            self.external_scripts.append(a["src"])
        if tag == "main":
            self.has_main = True
        if tag == "header":
            self.has_header = True
        if tag == "nav":
            self.has_nav = True
        if tag == "footer":
            self.has_footer = self.in_footer = True
        if tag == "form":
            self.forms.append(a)
        if tag == "div" and "banner" in (a.get("class") or ""):
            self.banner = True
        if tag not in ("meta", "link", "img", "br", "hr", "input", "source", "path", "svg"):
            self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "footer":
            self.in_footer = False
        if tag in self.tag_stack:
            while self.tag_stack and self.tag_stack[-1] != tag:
                self.tag_stack.pop()
                self.unclosed += 1
            if self.tag_stack:
                self.tag_stack.pop()

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        self.text_parts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def audit_page(path: Path, site_dir: Path, mode_expected: str | None) -> list[tuple[str, str]]:
    """Return [(level, message)] for one HTML page."""
    out: list[tuple[str, str]] = []
    raw = path.read_text(errors="replace")
    p = Page()
    p.feed(raw)
    name = path.name
    F = lambda m: out.append(("FAIL", f"{name}: {m}"))  # noqa: E731
    W = lambda m: out.append(("WARN", f"{name}: {m}"))  # noqa: E731

    if not raw.lstrip().lower().startswith("<!doctype html>"):
        F("missing <!DOCTYPE html>")
    if not p.lang:
        F("<html> missing lang attribute")
    if not p.charset:
        F("missing <meta charset>")
    if "width=device-width" not in p.meta.get("viewport", ""):
        F("missing responsive viewport meta")
    t = p.title.strip()
    if not t:
        F("missing <title>")
    elif not 10 <= len(t) <= 70:
        W(f"title length {len(t)} (aim 10–70): {t[:60]!r}")
    d = p.meta.get("description", "")
    if not d:
        F("missing meta description")
    elif not 50 <= len(d) <= 160:
        W(f"meta description length {len(d)} (aim 50–160)")
    h1s = p.h.count("h1")
    sections = raw.count('class="page"') if path.name == "preview.html" else 1
    if h1s != sections:
        F(f"{h1s} <h1> elements (need exactly {sections})")
    prev = 0
    for tag in p.h:
        lvl = int(tag[1])
        if prev and lvl > prev + 1:
            W(f"heading jumps h{prev} → h{lvl}")
            break
        prev = lvl
    if not p.skip_link:
        F("no skip-to-content link")
    for flag, label in [(p.has_main, "<main>"), (p.has_header, "<header>"), (p.has_footer, "<footer>"), (p.has_nav, "<nav>")]:
        if not flag:
            F(f"missing {label} landmark")
    if p.imgs_without_alt:
        F(f"{p.imgs_without_alt} <img> without alt")
    if p.inline_handlers:
        F(f"{p.inline_handlers} inline event handler attribute(s)")
    if p.external_scripts:
        F(f"external scripts: {p.external_scripts}")
    if p.unclosed:
        W(f"{p.unclosed} unbalanced tag(s) detected by parser")
    if len(raw) > 300_000:
        W(f"page is {len(raw) // 1024} KB (aim < 300 KB)")

    mode = p.meta.get("lindaai-mode", "")
    if mode_expected and mode != mode_expected:
        F(f"meta lindaai-mode is {mode!r}, expected {mode_expected!r}")
    if mode == "preview":
        if "noindex" not in p.meta.get("robots", ""):
            F("preview page is not noindex")
        if not p.banner:
            F("preview page has no preview banner")
        if not re.search(r"not been reviewed or approved|fictional business", p.text):
            F("preview banner lacks the not-approved/fictional disclosure")
    elif mode == "final":
        if "noindex" in p.meta.get("robots", ""):
            W("final page is still noindex")
        if p.banner:
            F("final page still shows the preview banner")

    txt = p.text
    if m := PLACEHOLDER.search(txt):
        F(f"placeholder text found: {m.group(0)!r}")
    verified = json.loads((site_dir / "site.json").read_text()).get("verified_claims", "") if (site_dir / "site.json").exists() else ""
    if not verified:
        for m in CLAIMS.finditer(txt):
            ctx = txt[max(0, m.start() - 140): m.end() + 40].replace("\n", " ")
            low = re.sub(r"\s+", " ", ctx.lower())
            if any(k in low for k in ("no claims about", "doesn't claim", "nothing here claims", "warranty", "hasn't been confirmed")):
                continue
            F(f"unverified credential claim {m.group(0)!r}: …{ctx.strip()}…")
            break
    if m := TESTIMONIAL.search(txt):
        F(f"testimonial/rating content present without verified reviews: {m.group(0)!r}")

    single = name == "preview.html"
    for href, a in p.links:
        if not href:
            F("<a> without href")
            continue
        if href.startswith(("http://", "https://")):
            if a.get("target") == "_blank" and "noopener" not in (a.get("rel") or ""):
                W(f"external link opens new tab without rel=noopener: {href[:60]}")
            continue
        if href.startswith(("mailto:", "tel:", "sms:", "#")):
            continue
        target = (path.parent / href.split("#")[0]).resolve()
        if href.split("#")[0] and not target.exists():
            F(f"broken internal link: {href}")
    for s in p.srcs:
        if not s.startswith(("http", "data:")) and not (path.parent / s).exists():
            F(f"missing asset: {s}")
    if not single:
        for req in FOOTER_LINKS:
            if not any(l.split("#")[0] == req for l in p.footer_links):
                F(f"footer does not link to {req}")
    else:
        for req in ("#faq", "#privacy", "#terms", "#accessibility", "#contact"):
            if req not in p.footer_links:
                F(f"footer does not link to {req}")
    if name in ("contact.html", "index.html", "preview.html") and not any(h.startswith("tel:") for h, _ in p.links):
        F("no tel: link")
    for f in p.forms:
        act = f.get("action", "")
        if not act or PLACEHOLDER.search(act) or "FORM_ID" in act:
            F(f"form with missing/placeholder action: {act!r}")
    return out


def audit_site(site_dir: Path) -> dict:
    findings: list[tuple[str, str]] = []
    pages = sorted(site_dir.glob("*.html"))
    mode = None
    if (site_dir / "site.json").exists():
        mode = json.loads((site_dir / "site.json").read_text()).get("mode")
    for req in REQUIRED_PAGES:
        if not (site_dir / req).exists():
            findings.append(("FAIL", f"required page missing: {req}"))
    if mode == "preview" and not (site_dir / "preview-notice.html").exists():
        findings.append(("FAIL", "preview-notice.html missing (owner claim/remove page)"))
    for pg in pages:
        findings.extend(audit_page(pg, site_dir, mode))
    fails = sum(1 for l, _ in findings if l == "FAIL")
    warns = sum(1 for l, _ in findings if l == "WARN")
    return {"site": site_dir.name, "mode": mode, "pages": len(pages), "fail": fails, "warn": warns,
            "status": "FAIL" if fails else "WARN" if warns else "PASS", "findings": findings}


def audit_email(path: Path, studio_cfg: dict) -> dict:
    txt = path.read_text()
    findings: list[tuple[str, str]] = []
    F = lambda m: findings.append(("FAIL", f"{path.name}: {m}"))  # noqa: E731
    W = lambda m: findings.append(("WARN", f"{path.name}: {m}"))  # noqa: E731
    head = txt.split("---")[1] if txt.startswith("---") and txt.count("---") >= 2 else ""
    subj = re.search(r"^subject:\s*(.+)$", head, re.M)
    if path.name.startswith(("0", "reply")):
        if not subj:
            F("no subject: line in front matter")
        else:
            s = subj.group(1).strip()
            if re.match(r"^(re|fwd?):", s, re.I):
                F(f"subject fakes a reply/forward: {s!r}")
            if s.isupper():
                F("subject is ALL CAPS")
            if len(s) > 60:
                W(f"subject is {len(s)} chars (aim ≤ 60)")
            if re.search(r"free!|act now|urgent|limited time|\$\$\$|!!", s, re.I):
                W(f"spam-trigger wording in subject: {s!r}")
        body = txt.split("---", 2)[-1] if head else txt
        addr_set = studio_cfg.get("postal_address", "") not in ("", "POSTAL_ADDRESS")
        if "{{postal_address}}" not in body and not (addr_set and studio_cfg["postal_address"] in body):
            F("no physical postal address (CAN-SPAM §5(a)(5)) — include {{postal_address}}")
        elif not addr_set:
            (F if SEND_READY else W)("studio.json postal_address is not set — sends are blocked until it is")
        if not re.search(r"reply .{0,20}(stop|unsubscribe|no thanks|remove)|unsubscribe|opt[- ]out", body, re.I):
            F("no clear opt-out instruction (CAN-SPAM requires one that works for 30 days)")
        if not re.search(r"(not|never|hasn't|hasn't been|has not been) (yet )?(been )?(reviewed|approved|affiliated|endorsed)|has not approved|isn't affiliated|is not affiliated|no relationship", body, re.I):
            F("missing line stating the preview is not approved by / affiliated with the business")
        if not re.search(r"\{\{(from_name|studio_name|offer_name)\}\}|LindaAI", body):
            F("sender not identified by name/company in body")
        if re.search(r"you (have )?no website|you don't have a website|your business has no website", body, re.I):
            W("asserts the business has no website — phrase as 'couldn't find' (enrichment can be wrong)")
        for var in set(re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", body)):
            if var not in ALLOWED_VARS:
                F(f"unknown template variable {{{{{var}}}}}")
        if PLACEHOLDER.search(re.sub(r"\{\{[^}]*\}\}", "", body)):
            F("placeholder text left in body")
        if len(body.split()) > 220:
            W(f"body is {len(body.split())} words (cold email lands better under ~150)")
    fails = sum(1 for l, _ in findings if l == "FAIL")
    warns = sum(1 for l, _ in findings if l == "WARN")
    return {"site": f"email:{path.name}", "mode": "email", "pages": 1, "fail": fails, "warn": warns,
            "status": "FAIL" if fails else "WARN" if warns else "PASS", "findings": findings}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("targets", nargs="*", help="site directories (default: every sites/*/)")
    p.add_argument("--no-emails", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--send-ready", action="store_true", help="fail unless email templates are fully sendable (postal address set)")
    args = p.parse_args()
    global SEND_READY
    SEND_READY = args.send_ready
    targets = [Path(t) for t in args.targets] or sorted(d for d in SITES.iterdir() if d.is_dir())
    results = [audit_site(t) for t in targets]
    studio_cfg = json.loads((ROOT / "config" / "studio.json").read_text())
    if not args.no_emails:
        results += [audit_email(e, studio_cfg) for e in sorted((ROOT / "emails").glob("*.md"))]
    REPORTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Website audit — {stamp}", "", "| Target | Mode | Pages | Fail | Warn | Status |", "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['site']} | {r['mode']} | {r['pages']} | {r['fail']} | {r['warn']} | **{r['status']}** |")
    lines.append("")
    for r in results:
        if r["findings"]:
            lines.append(f"## {r['site']}")
            lines += [f"- **{l}** {m}" for l, m in r["findings"]]
            lines.append("")
    (REPORTS / "audit-latest.md").write_text("\n".join(lines))
    (REPORTS / "audit-latest.json").write_text(json.dumps(results, indent=2))
    print("\n".join(lines[:4 + len(results)]))
    for r in results:
        for l, m in r["findings"]:
            print(f"  {l:4} {r['site']}: {m}")
    bad = any(r["status"] == "FAIL" or (args.strict and r["status"] == "WARN") for r in results)
    print(f"\nreport -> {REPORTS / 'audit-latest.md'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
