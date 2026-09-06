#!/usr/bin/env python3
"""Step 4 — generate a complete preview website for each lead.

Every site gets: home, services, about, FAQ, contact, privacy, terms, accessibility, and a
preview-notice page, plus a persistent preview banner and <meta name="robots" noindex>
so search engines never index a page about a business that has not approved it.

Modes
  preview (default)  banner + noindex + "template policy" notes. Safe to send to a prospect.
  final              banner removed, indexable, JSON-LD LocalBusiness + FAQPage added,
                     contact form enabled when lead has form_endpoint. Use after sign-off.

Usage
  python3 scripts/build_site.py --queue leads/build_queue.json            # all queued leads
  python3 scripts/build_site.py --csv leads/sample-leads.csv --single-file # + one-file previews
  python3 scripts/build_site.py --csv leads/sample-leads.csv --only pikes-peak-mobile-detailing-colorado-springs --mode final
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

from common import SITES, classify, industries, read_csv, slugify, studio, truthy

E = html.escape
YEAR = dt.date.today().year

PAGES = [  # (key, file, nav label)
    ("home", "index.html", "Home"),
    ("services", "services.html", "Services"),
    ("about", "about.html", "About"),
    ("faq", "faq.html", "FAQ"),
    ("contact", "contact.html", "Contact"),
]
LEGAL = [
    ("privacy", "privacy.html", "Privacy"),
    ("terms", "terms.html", "Terms"),
    ("accessibility", "accessibility.html", "Accessibility"),
    ("notice", "preview-notice.html", "About this preview"),
]

ICON = {
    "phone": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.6 10.8a15 15 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16zm.5-13H11v6l5.2 3.1.8-1.2-4.5-2.7z"/></svg>',
    "pin": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>',
    "mail": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5z"/></svg>',
    "check": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>',
}


# ------------------------------------------------------------------ helpers
def tel_href(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        d = "1" + d
    return f"tel:+{d}" if d else ""


def sms_href(phone: str) -> str:
    return tel_href(phone).replace("tel:", "sms:")


def parse_hours(s: str) -> list[tuple[str, str]]:
    rows = []
    for part in re.split(r"\s*;\s*", s or ""):
        m = re.match(r"^(\S+(?:\s*[–-]\s*\S+)?)\s+(.+)$", part.strip())
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def clamp(desc: str, n: int = 158) -> str:
    if len(desc) <= n:
        return desc
    cut = desc[: n - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def monogram(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if w.lower() not in {"and", "the", "of"}]
    return "".join(w[0] for w in words[:2]).upper() or "•"


def fonts_link(ind: dict) -> str:
    f = ind["fonts"]
    fam = lambda n, w: "family=" + n.replace(" ", "+") + f":wght@{w}"  # noqa: E731
    parts = [fam(f["display"], f["display_weights"])]
    if f["body"] != f["display"]:
        parts.append(fam(f["body"], f["body_weights"]))
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{"&".join(parts)}&display=swap">')


def css(ind: dict) -> str:
    p, f = ind["palette"], ind["fonts"]
    return f"""
:root{{--primary:{p['primary']};--accent:{p['accent']};--ink:{p['ink']};--paper:{p['paper']};--muted:{p['muted']};--panel:{p['panel']};
--display:'{f['display']}',Georgia,serif;--body:'{f['body']}',system-ui,-apple-system,Segoe UI,sans-serif;--max:1080px;--r:6px;color-scheme:light}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}
@media (prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}*{{transition:none!important;animation:none!important}}}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);font-size:1.05rem;line-height:1.6;-webkit-font-smoothing:antialiased}}
a{{color:var(--primary)}}a:focus-visible,button:focus-visible,summary:focus-visible{{outline:3px solid var(--accent);outline-offset:3px}}
img,svg{{max-width:100%}}svg{{fill:currentColor}}
.skip{{position:absolute;left:-999px;top:8px;background:var(--accent);color:#fff;padding:.5rem .8rem;border-radius:var(--r);z-index:200;font-weight:700}}.skip:focus{{left:8px}}
.wrap{{max-width:var(--max);margin:0 auto;padding:0 1.25rem}}
.banner{{background:var(--ink);color:var(--paper);font-size:.9rem;line-height:1.45;padding:.6rem 1rem;text-align:center}}
.banner a{{color:var(--paper);text-decoration:underline;text-underline-offset:2px;font-weight:600}}
.banner strong{{color:var(--accent)}}
header.site{{border-bottom:1px solid color-mix(in srgb,var(--ink) 12%,transparent);background:var(--paper);position:sticky;top:0;z-index:50}}
.bar{{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.8rem 0;flex-wrap:wrap}}
.brand{{display:flex;align-items:center;gap:.7rem;text-decoration:none;color:var(--ink)}}
.mono{{width:42px;height:42px;display:grid;place-items:center;background:var(--primary);color:var(--paper);font-family:var(--display);font-weight:700;font-size:1.05rem;border-radius:var(--r);letter-spacing:.02em;flex:none}}
.brand b{{font-family:var(--display);font-weight:700;font-size:1.15rem;line-height:1.1}}
.brand small{{display:block;color:var(--muted);font-size:.78rem;font-weight:400;letter-spacing:.06em;text-transform:uppercase}}
nav.main ul{{list-style:none;margin:0;padding:0;display:flex;gap:.2rem;flex-wrap:wrap}}
nav.main a{{display:block;padding:.45rem .7rem;text-decoration:none;color:var(--ink);border-radius:var(--r);font-weight:600;font-size:.95rem}}
nav.main a:hover{{background:var(--panel)}}nav.main a[aria-current=page]{{box-shadow:inset 0 -3px 0 var(--accent)}}
.call{{display:inline-flex;align-items:center;gap:.45rem;background:var(--primary);color:var(--paper);padding:.55rem .9rem;border-radius:var(--r);text-decoration:none;font-weight:700;white-space:nowrap}}
.call svg{{width:18px;height:18px}}
main{{display:block}}
.hero{{padding:3.5rem 0 3rem;display:grid;grid-template-columns:1.25fr .9fr;gap:2.5rem;align-items:center}}
.eyebrow{{color:var(--accent);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:.78rem;margin:0 0 .6rem}}
h1,h2,h3{{font-family:var(--display);line-height:1.1;text-wrap:balance;margin:0 0 .6rem}}
h1{{font-size:clamp(2.1rem,5vw,3.4rem);font-weight:800}}h2{{font-size:clamp(1.5rem,3vw,2.1rem);font-weight:700}}h3{{font-size:1.15rem;font-weight:700}}
.lead{{font-size:1.2rem;color:color-mix(in srgb,var(--ink) 78%,var(--muted));max-width:38rem;margin:0 0 1.4rem}}
.actions{{display:flex;gap:.7rem;flex-wrap:wrap}}
.btn{{display:inline-flex;align-items:center;gap:.5rem;padding:.8rem 1.25rem;border-radius:var(--r);text-decoration:none;font-weight:700;border:2px solid var(--primary);color:var(--primary);background:transparent}}
.btn.primary{{background:var(--accent);border-color:var(--accent);color:#fff}}
.btn svg{{width:18px;height:18px}}
.facts{{background:var(--panel);border-left:6px solid var(--accent);border-radius:var(--r);padding:1.25rem 1.4rem;display:grid;gap:.9rem}}
.fact{{display:grid;grid-template-columns:22px 1fr;gap:.7rem;align-items:start}}
.fact svg{{width:22px;height:22px;color:var(--primary);margin-top:.15rem}}
.fact b{{display:block;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
section.block{{padding:3rem 0}}section.alt{{background:var(--panel)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.1rem;margin:0;padding:0;list-style:none}}
.card{{background:var(--paper);border:1px solid color-mix(in srgb,var(--ink) 12%,transparent);border-radius:var(--r);padding:1.2rem 1.25rem}}
section.alt .card{{border-color:transparent}}
.card h3,.card h2{{margin-bottom:.35rem;font-size:1.15rem}}.card p{{margin:0;color:color-mix(in srgb,var(--ink) 80%,var(--muted))}}
.steps{{counter-reset:s;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1.2rem;padding:0;margin:0;list-style:none}}
.steps li{{counter-increment:s;padding-top:.5rem;border-top:3px solid var(--accent)}}
.steps li::before{{content:counter(s,decimal-leading-zero);font-family:var(--display);font-weight:800;color:var(--accent);font-size:1.4rem;display:block;margin-bottom:.3rem}}
details{{border-bottom:1px solid color-mix(in srgb,var(--ink) 14%,transparent);padding:.9rem 0}}
summary{{cursor:pointer;font-weight:700;font-size:1.08rem;font-family:var(--display);list-style:none;display:flex;justify-content:space-between;gap:1rem}}
summary::-webkit-details-marker{{display:none}}summary::after{{content:"+";color:var(--accent);font-weight:800;font-size:1.3rem;line-height:1}}
details[open] summary::after{{content:"–"}}details p{{margin:.6rem 0 0;max-width:60ch}}
.band{{background:var(--primary);color:var(--paper);padding:3rem 0;text-align:center}}
.band h2{{color:var(--paper)}}.band .btn{{border-color:var(--paper);color:var(--paper)}}.band .btn.primary{{background:var(--accent);border-color:var(--accent)}}
.prose{{max-width:68ch}}.prose h2{{margin-top:2rem;font-size:1.4rem}}.prose p,.prose li{{color:color-mix(in srgb,var(--ink) 85%,var(--muted))}}
.note{{background:var(--panel);border-left:6px solid var(--accent);padding:1rem 1.2rem;border-radius:var(--r);margin:1.5rem 0}}
table{{border-collapse:collapse;width:100%;max-width:32rem}}td,th{{text-align:left;padding:.5rem .6rem;border-bottom:1px solid color-mix(in srgb,var(--ink) 14%,transparent)}}th{{font-weight:700;width:40%}}
.contact-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.1rem;list-style:none;padding:0;margin:1.5rem 0}}
.contact-grid a{{font-weight:700;word-break:break-word}}
form.contact{{display:grid;gap:.9rem;max-width:34rem}}form.contact label{{font-weight:600}}form.contact input,form.contact textarea{{width:100%;padding:.7rem;border:1px solid var(--muted);border-radius:var(--r);font:inherit}}
footer.site{{border-top:1px solid color-mix(in srgb,var(--ink) 12%,transparent);padding:2.2rem 0;color:var(--muted);font-size:.92rem}}
footer .cols{{display:flex;justify-content:space-between;gap:2rem;flex-wrap:wrap}}
footer ul{{list-style:none;margin:0;padding:0;display:flex;gap:.3rem 1.1rem;flex-wrap:wrap}}footer a{{color:var(--ink)}}
.page-head{{padding:3rem 0 1rem}}
@media (max-width:820px){{.hero{{grid-template-columns:1fr;padding-top:2.2rem}}.bar{{display:grid;grid-template-columns:1fr auto;gap:.5rem .8rem}}nav.main{{grid-column:1/-1}}nav.main a{{padding:.4rem .55rem;font-size:.9rem}}.call span{{display:none}}}}
"""


# ------------------------------------------------------------------ page chrome
class Site:
    def __init__(self, lead: dict, mode: str, single: bool):
        self.lead = lead
        self.mode = mode
        self.single = single
        self.studio = studio()
        lib = industries()
        self.ind_key = lead.get("industry") or classify(lead["name"], lib)
        self.ind = lib["industries"].get(self.ind_key, lib["industries"]["generic"])
        self.name = lead["name"]
        self.city = lead.get("city") or "Colorado"
        self.state = lead.get("state") or "CO"
        self.phone = lead.get("phone", "")
        self.email = lead.get("email", "")
        self.sample = truthy(lead.get("sample", ""))
        self.slug = lead.get("slug") or slugify(f"{self.name}-{self.city}")
        self.preview = mode == "preview"
        self.address = ", ".join(x for x in [lead.get("address1", ""), lead.get("address2", "")] if x)
        self.hours = parse_hours(lead.get("hours", ""))

    def fmt(self, s: str) -> str:
        return s.format(name=self.name, city=self.city)

    def href(self, key_or_file: str) -> str:
        if self.single:
            return "#" + key_or_file.replace(".html", "").replace("index", "home").replace("preview-notice", "notice")
        return key_or_file

    def head(self, title: str, desc: str, css_inline: str | None) -> str:
        robots = '<meta name="robots" content="noindex,nofollow">' if self.preview else '<meta name="robots" content="index,follow">'
        style = f"<style>{css_inline}</style>" if css_inline is not None else '<link rel="stylesheet" href="styles.css">'
        return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{E(title)}</title><meta name="description" content="{E(desc)}">{robots}'
                f'<meta name="lindaai-mode" content="{self.mode}"><meta name="generator" content="{E(self.studio["offer_name"])}">'
                f'{fonts_link(self.ind)}{style}</head>')

    def banner(self) -> str:
        if not self.preview:
            return ""
        st = self.studio
        if self.sample:
            txt = (f'<strong>Sample preview.</strong> {E(self.name)} is a fictional business used to demonstrate '
                   f'{E(st["offer_name"])} websites. Phone numbers and addresses are not real.')
        else:
            txt = (f'<strong>Preview.</strong> This website was prepared for {E(self.name)} by {E(st["offer_name"])} and has '
                   f'<u>not</u> been reviewed or approved by the business. Details may be incomplete or inaccurate; confirm anything '
                   f'important with the business directly.')
        return f'<div class="banner" role="note">{txt} <a href="{self.href("preview-notice.html")}">Business owner? Claim, edit, or remove this preview.</a></div>'

    def header(self, current: str) -> str:
        items = ""
        for k, f, lbl in PAGES:
            cur = ' aria-current="page"' if k == current else ""
            items += f'<li><a href="{self.href(f)}"{cur}>{E(lbl)}</a></li>'
        call = f'<a class="call" href="{tel_href(self.phone)}">{ICON["phone"]}<span>{E(self.phone)}</span></a>' if self.phone else ""
        return (f'<header class="site"><div class="wrap bar"><a class="brand" href="{self.href("index.html")}">'
                f'<span class="mono" aria-hidden="true">{E(monogram(self.name))}</span><span><b>{E(self.name)}</b>'
                f'<small>{E(self.ind["label"])} · {E(self.city)}, {E(self.state)}</small></span></a>'
                f'<nav class="main" aria-label="Primary"><ul>{items}</ul></nav>{call}</div></header>')

    def footer(self) -> str:
        st = self.studio
        links = "".join(f'<li><a href="{self.href(f)}">{E(lbl)}</a></li>' for _, f, lbl in PAGES + LEGAL)
        credit = (f'Website preview by <a href="{E(st["website"])}">{E(st["offer_name"])}</a>' if self.preview
                  else f'Website by <a href="{E(st["website"])}">{E(st["offer_name"])}</a>')
        addr = f" · {E(self.address)}, {E(self.city)}, {E(self.state)} {E(self.lead.get('zip', ''))}" if self.address else ""
        return (f'<footer class="site"><div class="wrap cols"><div>© {YEAR} {E(self.name)}{addr}<br>{credit}</div>'
                f'<ul>{links}</ul></div></footer>')

    # ---------------------------------------------------------------- pages
    def page_home(self) -> str:
        i = self.ind
        cta = []
        if self.phone:
            cta.append(f'<a class="btn primary" href="{tel_href(self.phone)}">{ICON["phone"]}Call {E(self.phone)}</a>')
            cta.append(f'<a class="btn" href="{sms_href(self.phone)}">Text us</a>')
        cta.append(f'<a class="btn" href="{self.href("contact.html")}">{E(i["cta"])}</a>')
        hours = "; ".join(f"{d} {h}" for d, h in self.hours[:2]) or "Call for current hours"
        facts = (f'<div class="fact">{ICON["pin"]}<div><b>Service area</b>{E(self.city)}, {E(self.state)} and nearby</div></div>'
                 f'<div class="fact">{ICON["clock"]}<div><b>Hours</b>{E(hours)}</div></div>')
        if self.phone:
            facts += f'<div class="fact">{ICON["phone"]}<div><b>Call or text</b><a href="{tel_href(self.phone)}">{E(self.phone)}</a></div></div>'
        cards = "".join(f'<li class="card"><h3>{E(t)}</h3><p>{E(self.fmt(d))}</p></li>' for t, d in i["services"][:6])
        faqs = "".join(f'<details><summary>{E(q)}</summary><p>{E(self.fmt(a))}</p></details>' for q, a in i["faq"][:3])
        return f"""
<section class="wrap hero"><div><p class="eyebrow">{E(i['label'])} · {E(self.city)}, Colorado</p>
<h1>{E(self.fmt(i['hero']))}</h1><p class="lead">{E(self.fmt(i['tagline']))}</p><div class="actions">{''.join(cta)}</div></div>
<aside class="facts" aria-label="Quick facts">{facts}</aside></section>
<section class="block alt"><div class="wrap"><p class="eyebrow">What we do</p><h2>Services</h2><ul class="grid">{cards}</ul>
<p style="margin-top:1.2rem"><a class="btn" href="{self.href('services.html')}">All services</a></p></div></section>
<section class="block"><div class="wrap"><p class="eyebrow">How it works</p><h2>Three steps, no runaround</h2><ol class="steps">
<li><h3>Reach out</h3><p>Call, text, or email with what you need. A photo helps.</p></li>
<li><h3>Confirm details and price</h3><p>You get a clear scope and price before anything starts.</p></li>
<li><h3>Get it done</h3><p>Work is scheduled, finished, and walked through with you.</p></li></ol></div></section>
<section class="block alt"><div class="wrap"><p class="eyebrow">Questions</p><h2>Frequently asked</h2>{faqs}
<p style="margin-top:1.2rem"><a href="{self.href('faq.html')}">See all questions</a></p></div></section>
<section class="band"><div class="wrap"><h2>Ready when you are</h2><p>Reach {E(self.name)} today.</p><div class="actions" style="justify-content:center">{''.join(cta[:1] or cta)}<a class="btn" href="{self.href('contact.html')}">Contact page</a></div></div></section>"""

    def page_services(self) -> str:
        cards = "".join(f'<li class="card"><h2>{E(t)}</h2><p>{E(self.fmt(d))}</p></li>' for t, d in self.ind["services"])
        return f"""<section class="wrap page-head"><p class="eyebrow">Services</p><h1>What {E(self.name)} does</h1>
<p class="lead">{E(self.fmt(self.ind['tagline']))}</p></section>
<section class="block"><div class="wrap"><ul class="grid">{cards}</ul>
<div class="note"><b>Don't see it listed?</b> Ask. If it's outside what we do, we'll say so and point you to someone who does it well.</div>
<div class="actions"><a class="btn primary" href="{self.href('contact.html')}">{E(self.ind['cta'])}</a></div></div></section>"""

    def page_about(self) -> str:
        year = (self.lead.get("form_date") or "")[:4]
        reg = (f' {E(self.name)} is registered with the Colorado Secretary of State' + (f' (formed {E(year)})' if year else "") + "."
               if self.lead.get("entity_id") else "")
        preview_note = ("<div class=\"note\"><b>This page is a starting point.</b> The owner's story, the crew, photos of real work, "
                        "and what makes the business different get written together before launch. Nothing here claims credentials, "
                        "awards, or experience that hasn't been confirmed with the owner.</div>") if self.preview else ""
        return f"""<section class="wrap page-head"><p class="eyebrow">About</p><h1>About {E(self.name)}</h1></section>
<section class="block"><div class="wrap prose"><p>{E(self.name)} is a {E(self.ind['label'].lower())} business based in {E(self.city)}, Colorado.{reg}</p>
<p>{E(self.fmt(self.ind['tagline']))} The goal is simple: clear communication, fair pricing explained up front, and work that holds up.</p>
{preview_note}
<h2>Service area</h2><p>{E(self.city)} and the surrounding communities. If you're outside that area, reach out; we'll tell you honestly whether we can help.</p>
<h2>How to reach us</h2><p>Everything is on the <a href="{self.href('contact.html')}">contact page</a>: phone, text, email, and hours.</p></div></section>"""

    def page_faq(self) -> str:
        items = "".join(f'<details><summary>{E(q)}</summary><p>{E(self.fmt(a))}</p></details>' for q, a in self.ind["faq"])
        extra = [
            ("How do I know this website is legitimate?",
             f"This site is a preview prepared for {self.name}. Please confirm details with the business directly before relying on them."
             if self.preview else f"This is the official website of {self.name}. Contact details are on the contact page."),
            ("Do you collect my information on this site?",
             "No forms or trackers are used on this preview. If you call, text, or email, we only use that information to respond to you. See the privacy page."),
        ]
        items += "".join(f'<details><summary>{E(q)}</summary><p>{E(a)}</p></details>' for q, a in extra)
        return f"""<section class="wrap page-head"><p class="eyebrow">FAQ</p><h1>Frequently asked questions</h1>
<p class="lead">Straight answers to the questions we hear most.</p></section>
<section class="block"><div class="wrap prose">{items}
<div class="note">Still have a question? <a href="{self.href('contact.html')}">Ask us directly.</a></div></div></section>"""

    def page_contact(self) -> str:
        cards = []
        if self.phone:
            cards.append(f'<li class="card"><h2>Call or text</h2><p><a href="{tel_href(self.phone)}">{E(self.phone)}</a></p><p style="margin-top:.4rem"><a href="{sms_href(self.phone)}">Send a text</a></p></li>')
        if self.email:
            cards.append(f'<li class="card"><h2>Email</h2><p><a href="mailto:{E(self.email)}">{E(self.email)}</a></p></li>')
        if self.address:
            q = E(f"{self.name} {self.address} {self.city} {self.state}".replace(" ", "+"))
            cards.append(f'<li class="card"><h2>Address</h2><p>{E(self.address)}<br>{E(self.city)}, {E(self.state)} {E(self.lead.get("zip", ""))}</p><p style="margin-top:.4rem"><a href="https://www.google.com/maps/search/?api=1&amp;query={q}" rel="noopener noreferrer" target="_blank">Open in Maps</a></p></li>')
        hours = "".join(f"<tr><th scope=\"row\">{E(d)}</th><td>{E(h)}</td></tr>" for d, h in self.hours)
        hours_html = f'<h2>Hours</h2><table><caption class="eyebrow" style="text-align:left;caption-side:top">Typical hours</caption>{hours}</table>' if hours else '<h2>Hours</h2><p>Call or text for current hours.</p>'
        form = ""
        ep = self.lead.get("form_endpoint", "")
        if not self.preview and ep:
            form = f"""<h2>Send a message</h2><form class="contact" method="POST" action="{E(ep)}">
<div><label for="f-name">Your name</label><input id="f-name" name="name" required autocomplete="name"></div>
<div><label for="f-phone">Phone</label><input id="f-phone" name="phone" type="tel" autocomplete="tel"></div>
<div><label for="f-msg">What do you need?</label><textarea id="f-msg" name="message" rows="5" required></textarea></div>
<button class="btn primary" type="submit">Send</button></form>"""
        elif self.preview:
            form = '<div class="note">A contact form is added when the site goes live. For now, call, text, or email.</div>'
        return f"""<section class="wrap page-head"><p class="eyebrow">Contact</p><h1>Reach {E(self.name)}</h1>
<p class="lead">Call or text is fastest. Email works too.</p></section>
<section class="block"><div class="wrap"><ul class="contact-grid">{''.join(cards)}</ul><div class="prose">{hours_html}{form}</div></div></section>"""

    def page_privacy(self) -> str:
        st = self.studio
        tmpl_note = ('<div class="note"><b>Template policy.</b> This privacy policy is a standard small-business template prepared '
                     f'with the preview and will be reviewed with {E(self.name)} before the site goes live.</div>') if self.preview else ""
        preview_who = (" It is currently a preview operated by " + E(st["legal_name"]) + " on the business's behalf pending approval.") if self.preview else ""
        return f"""<section class="wrap page-head"><p class="eyebrow">Legal</p><h1>Privacy policy</h1><p class="lead">Effective {E(dt.date.today().strftime('%B %-d, %Y'))}</p></section>
<section class="block"><div class="wrap prose">{tmpl_note}
<h2>Who we are</h2><p>This website is for {E(self.name)}, a business located in {E(self.city)}, Colorado.{preview_who}</p>
<h2>What we collect</h2><p>This site does not use accounts, analytics trackers, or advertising cookies. If you call, text, or email us, we receive the contact details and message you choose to send, and we use them only to respond and provide the service you asked about.</p>
<p>Our web host may keep standard server logs (IP address, browser type, pages requested, timestamps) for security and reliability. Fonts are loaded from Google Fonts, which receives your IP address when the font file is requested; see Google's privacy policy for details.</p>
<h2>How we use and share information</h2><p>We use your information to answer questions, schedule and perform work, send invoices, and keep records required by law. We do not sell personal information. We share it only with service providers who help us operate (for example a phone or email provider) or when the law requires.</p>
<h2>Retention</h2><p>We keep messages and job records as long as needed for the work and for tax and legal purposes, then delete or anonymize them.</p>
<h2>Your choices</h2><p>You can ask us what information we hold about you, ask us to correct it, or ask us to delete it where we are not required to keep it. Contact us using the details on the <a href="{self.href('contact.html')}">contact page</a>.</p>
<h2>Children</h2><p>This site is not directed at children under 13 and we do not knowingly collect their information.</p>
<h2>Changes</h2><p>If this policy changes, the new version will be posted here with a new effective date.</p>
<h2>Contact</h2><p>Questions about this policy: {'<a href="mailto:' + E(self.email) + '">' + E(self.email) + '</a>' if self.email else 'use the contact page'}.{' Questions about the preview itself: <a href="mailto:' + E(st['contact_email']) + '">' + E(st['contact_email']) + '</a>.' if self.preview else ''}</p></div></section>"""

    def page_terms(self) -> str:
        tmpl_note = ('<div class="note"><b>Template terms.</b> Standard website terms prepared with the preview; reviewed with '
                     f'{E(self.name)} before launch.</div>') if self.preview else ""
        return f"""<section class="wrap page-head"><p class="eyebrow">Legal</p><h1>Website terms of use</h1><p class="lead">Effective {E(dt.date.today().strftime('%B %-d, %Y'))}</p></section>
<section class="block"><div class="wrap prose">{tmpl_note}
<h2>Information only</h2><p>Content on this site describes services generally. It is not a binding quote or contract. Pricing, availability, and scope are confirmed in writing before work begins.</p>
<h2>Estimates and scheduling</h2><p>Any estimate given by phone, text, or email is based on the information you provide and may change after an on-site look. Appointment times are confirmed by the business.</p>
<h2>No warranty on the website</h2><p>We work to keep this site accurate and available, but it is provided "as is" without warranties of any kind. Warranties on actual work performed, if any, are stated in your written agreement.</p>
<h2>Intellectual property</h2><p>Text, logos, and layout on this site belong to {E(self.name)} or its licensors and may not be copied for commercial use without permission.</p>
<h2>Links</h2><p>Links to third-party sites (such as map services) are provided for convenience. We are not responsible for their content or practices.</p>
<h2>Governing law</h2><p>These terms are governed by the laws of the State of Colorado.</p>
<h2>Changes</h2><p>We may update these terms; the current version is always the one posted here.</p>
<h2>Contact</h2><p>Questions about these terms: see the <a href="{self.href('contact.html')}">contact page</a>.</p></div></section>"""

    def page_accessibility(self) -> str:
        st = self.studio
        return f"""<section class="wrap page-head"><p class="eyebrow">Accessibility</p><h1>Accessibility statement</h1></section>
<section class="block"><div class="wrap prose">
<p>{E(self.name)} wants everyone to be able to use this website, including people who use screen readers, keyboard navigation, or magnification. This site is built toward the Web Content Accessibility Guidelines (WCAG) 2.1 at level AA.</p>
<h2>What we've done</h2><ul>
<li>Semantic headings, landmarks, and a skip-to-content link on every page</li>
<li>Visible keyboard focus on links, buttons, and expandable questions</li>
<li>Color contrast chosen to meet AA for body text and controls</li>
<li>Text that scales with browser zoom and reflows on small screens</li>
<li>No autoplaying media, no motion that can't be reduced by your system setting</li></ul>
<h2>Known limitations</h2><p>Third-party services linked from this site (such as map providers) have their own accessibility practices that we don't control.</p>
<h2>Tell us</h2><p>If anything on this site is hard to use, contact us via the <a href="{self.href('contact.html')}">contact page</a>{' or email <a href="mailto:' + E(st['contact_email']) + '">' + E(st['contact_email']) + '</a>' if self.preview else ''} and we'll fix it or provide the information another way.</p></div></section>"""

    def page_notice(self) -> str:
        st = self.studio
        if self.sample:
            who = (f"<p><b>{E(self.name)} is a fictional business.</b> This site exists to show what a {E(st['offer_name'])} "
                   "preview looks like. The phone number, email, and address are placeholders and do not reach anyone.</p>")
        else:
            who = (f"<p>{E(st['legal_name'])} built this preview for <b>{E(self.name)}</b> using public business-registration "
                   "records and general information about the trade. The business did not request it and has not approved it. "
                   "No payment was requested to create it, and it will be edited or taken down promptly on request from the owner.</p>")
        return f"""<section class="wrap page-head"><p class="eyebrow">About this preview</p><h1>Why this website exists</h1></section>
<section class="block"><div class="wrap prose">{who}
<h2>What this preview is not</h2><ul>
<li>It is <b>not</b> the official website of {E(self.name)} and is <b>not</b> endorsed by the business.</li>
<li>It makes <b>no claims</b> about licensing, insurance, certifications, awards, or years in business.</li>
<li>It is marked <code>noindex</code> so search engines are asked not to list it.</li></ul>
<h2>If you own {E(self.name)}</h2><ol class="steps" style="margin:1rem 0 2rem">
<li><h3>Claim it</h3><p>Email <a href="mailto:{E(st['contact_email'])}?subject={E('Preview site: ' + self.name)}">{E(st['contact_email'])}</a> from a business address or call from the business phone.</p></li>
<li><h3>Make it yours</h3><p>We correct details, add your photos, hours, services, and real reviews, and connect a domain in <b>your</b> name.</p></li>
<li><h3>Or remove it</h3><p>Say the word and the preview comes down within one business day. No hard feelings.</p></li></ol>
<h2>Who built it</h2><p>{E(st['legal_name'])}, a {E(st['state_of_formation'])} company · <a href="{E(st['website'])}">{E(st['website'].replace('https://', ''))}</a> · <a href="mailto:{E(st['contact_email'])}">{E(st['contact_email'])}</a></p></div></section>"""

    # ---------------------------------------------------------------- assembly
    def pages(self) -> dict[str, tuple[str, str, str]]:
        n, c, lbl = self.name, self.city, self.ind["label"]
        return {k: (t, clamp(d), b) for k, (t, d, b) in {
            "home": (f"{n} · {lbl} in {c}, CO", f"{n}: {self.fmt(self.ind['tagline'])} Serving {c}, Colorado. Call or text for a quote.", self.page_home()),
            "services": (f"Services · {n}", f"{lbl} services offered by {n} in {c}, Colorado, with plain-language descriptions of each.", self.page_services()),
            "about": (f"About · {n}", f"About {n}, a {lbl.lower()} business based in {c}, Colorado, and the area it serves.", self.page_about()),
            "faq": (f"FAQ · {n}", f"Answers to common questions about {n}: pricing, scheduling, service area, and more.", self.page_faq()),
            "contact": (f"Contact · {n}", f"Call, text, or email {n} in {c}, Colorado. Hours, address, and directions.", self.page_contact()),
            "privacy": (f"Privacy policy · {n}", f"How the {n} website handles the information you share when you contact the business.", self.page_privacy()),
            "terms": (f"Terms of use · {n}", f"Website terms of use for {n}: information only, estimates, intellectual property, and governing law.", self.page_terms()),
            "accessibility": (f"Accessibility · {n}", f"Accessibility statement for the {n} website and how to report a problem.", self.page_accessibility()),
            "notice": (f"About this preview · {n}", f"Why a preview website exists for {n}, what it does not claim, and how the owner can claim or remove it.", self.page_notice()),
        }.items()}

    def file_for(self, key: str) -> str:
        return dict((k, f) for k, f, _ in PAGES + LEGAL)[key]

    def write_multi(self, out: Path) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        (out / "styles.css").write_text(css(self.ind))
        written = []
        for key, (title, desc, body) in self.pages().items():
            doc = (self.head(title, desc, None) + "<body>" + '<a class="skip" href="#main">Skip to content</a>' + self.banner()
                   + self.header(key) + f'<main id="main">{body}</main>' + self.footer() + "</body></html>")
            p = out / self.file_for(key)
            p.write_text(doc)
            written.append(p)
        (out / "site.json").write_text(json.dumps({**self.lead, "industry": self.ind_key, "mode": self.mode,
                                                   "generated": dt.datetime.now().isoformat(timespec="seconds")}, indent=2))
        return written

    def write_single(self, out: Path) -> Path:
        self.single = True
        title, desc, _ = self.pages()["home"]
        sections = []
        for key, (_, _, body) in self.pages().items():
            sections.append(f'<section class="page" id="{key}" data-title="{E(title if key == "home" else key)}">{body}</section>')
        js = """<script>(function(){document.documentElement.classList.add('js');
var pages=[].slice.call(document.querySelectorAll('.page'));var links=[].slice.call(document.querySelectorAll('nav.main a'));
function show(){var id=(location.hash||'#home').slice(1);if(!document.getElementById(id))id='home';
pages.forEach(function(p){p.classList.toggle('active',p.id===id)});
links.forEach(function(a){if(a.getAttribute('href')==='#'+id)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
window.scrollTo(0,0);document.getElementById('main').focus({preventScroll:true});}
window.addEventListener('hashchange',show);show();})();</script>"""
        extra_css = css(self.ind) + ".js .page:not(.active){display:none}#main:focus{outline:none}"
        doc = (self.head(title, desc, extra_css) + "<body>" + '<a class="skip" href="#main">Skip to content</a>' + self.banner()
               + self.header("home") + f'<main id="main" tabindex="-1">{"".join(sections)}</main>' + self.footer() + js + "</body></html>")
        out.mkdir(parents=True, exist_ok=True)
        p = out / "preview.html"
        p.write_text(doc)
        self.single = False
        return p


def write_gallery(sites_dir: Path) -> None:
    st = studio()
    rows = []
    for sj in sorted(sites_dir.glob("*/site.json")):
        d = json.loads(sj.read_text())
        slug = sj.parent.name
        tag = "sample" if truthy(d.get("sample", "")) else d.get("mode", "preview")
        rows.append(f'<li><a href="{slug}/">{E(d["name"])}</a> <small>{E(d.get("city", ""))}, {E(d.get("state", "CO"))} · {E(d.get("industry", ""))} · {tag}</small>'
                    + (f' · <a href="{slug}/preview.html">one-page preview</a>' if (sj.parent / "preview.html").exists() else "") + "</li>")
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Preview sites</title><meta name="robots" content="noindex,nofollow"><meta name="description" content="Index of preview websites generated by {E(st['offer_name'])}.">
<style>body{{font-family:system-ui,sans-serif;max-width:720px;margin:3rem auto;padding:0 1rem;line-height:1.6;color:#1b1f24;background:#fff}}li{{margin:.5rem 0}}small{{color:#666}}</style></head>
<body><h1>Preview sites</h1><p>{len(rows)} generated site(s). Each carries a preview banner and is marked noindex until the owner approves it.</p><ul>{''.join(rows)}</ul></body></html>"""
    (sites_dir / "index.html").write_text(doc)


def load_leads(args) -> list[dict]:
    if args.queue:
        return json.loads(Path(args.queue).read_text())
    return read_csv(Path(args.csv))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--queue", help="build_queue.json from score_leads.py")
    src.add_argument("--csv", help="CSV of leads (see leads/sample-leads.csv for columns)")
    p.add_argument("--mode", choices=["preview", "final"], default="preview")
    p.add_argument("--out", default=str(SITES), help="output root (default: sites/ at repo root)")
    p.add_argument("--single-file", action="store_true", help="also write preview.html (all pages in one file)")
    p.add_argument("--only", nargs="*", help="slugs to build")
    p.add_argument("--limit", type=int, default=100)
    args = p.parse_args()
    out_root = Path(args.out)
    built = 0
    for lead in load_leads(args)[: args.limit]:
        lead["slug"] = lead.get("slug") or slugify(f"{lead['name']}-{lead.get('city', '')}")
        if args.only and lead["slug"] not in args.only:
            continue
        site = Site(lead, args.mode, single=False)
        files = site.write_multi(out_root / lead["slug"])
        if args.single_file:
            files.append(site.write_single(out_root / lead["slug"]))
        built += 1
        print(f"built {lead['slug']}  ({site.ind_key}, {args.mode}, {len(files)} files)", file=sys.stderr)
    write_gallery(out_root)
    print(f"{built} site(s) -> {out_root}", file=sys.stderr)


if __name__ == "__main__":
    main()
