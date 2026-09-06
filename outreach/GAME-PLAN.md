# Game plan — Colorado "no website" preview-site campaign

**Goal:** turn public Colorado business records into paying website clients, with previews good
enough that the owner's first reaction is "that's better than what I'd have done," and a process
clean enough that nobody ever has a reason to complain.

**Where things stand (2026-09-06):** pipeline, generator, auditor, emails, and three demo sites are
built and audited clean on branch `claude/colorado-business-websites-4j2uy7`. The live directory
pull is blocked from cloud sessions by the environment's network policy, so Phase 1 runs on the
office Mac (or after the allowlist is widened). A weekly Routine is scheduled to run the search.

---

## Phase 0 — Owner decisions (15 minutes, blocks everything)
1. **Postal address** → `outreach/config/studio.json → postal_address`. Legally required in every
   email; the auditor fails the templates until it's set. A UPS Store box is fine.
2. **Sending mailbox.** Not `support@lindaai-brain.com` and not the personal Gmail. Buy a
   secondary domain (e.g. `lindaaisites.com`), set up Google Workspace or Zoho, add SPF/DKIM/DMARC,
   warm it two weeks at 10 emails/day. Cold email on the main brand domain risks its deliverability.
3. **Pricing.** Defaults in `studio.json`: $497 setup + $49/mo care, or $997 one-time with full
   transfer, domain year one included. Change if you want; the templates read from the file.
4. **Network policy.** Either run Phases 1–2 on the office Mac, or in the cloud environment
   "Sauce Claude" widen the allowlist to: `data.colorado.gov`, `places.googleapis.com`,
   `html.duckduckgo.com`, plus any registrar/host you pick. (claude.ai/code → Environments.)

## Phase 1 — Research (agent, weekly, automated)
- `fetch_co_businesses.py`: all Good-Standing entities with a Colorado principal address, formed in
  the last 3 years, in 38 Front Range / Western Slope cities, filtered to 17 service industries
  (plumbing, HVAC, electrical, roofing, landscaping, cleaning, painting, remodeling, auto, salon,
  food, fitness, pets, moving, handyman, tree, generic). Excludes holdings/real-estate/finance/
  legal/medical/cannabis/etc.
- `enrich_leads.py`: Google Places (best signal; ~$0.03/lookup) → website? phone? reviews?
  Fallbacks: DuckDuckGo + domain guessing. Anything ambiguous stays `unknown`.
- `score_leads.py`: 0–100. Tier A ≥75 (no site, high-ticket trade, reviews, phone) goes first.
- Output: `leads/03_scored.csv` + `build_queue.json`. Expect roughly 2–5% of pulled entities to
  land in Tier A/B; a 3-year pull across the target cities should yield several hundred.

## Phase 2 — Build + audit (agent, automated)
- `build_site.py` makes a 9-page preview per lead: home, services, about, FAQ, contact, privacy,
  terms, accessibility, "about this preview" (claim/remove page). Persistent preview banner,
  `noindex`, no credential claims, no fake reviews, industry palette + type pairing.
- `audit_site.py --strict` must pass: structure, required pages, disclosures, placeholders,
  claims, links, hygiene. The email templates are audited in the same run.
- Previews deploy with the repo to `lindaai-brain.com/sites/<slug>/` (GitHub Pages) once the
  branch merges to `main`. One-file `preview.html` is also produced for phone review.

## Phase 3 — You test (owner, 1 hour)
- Open the three demo previews on your phone (artifact links in the session, or `sites/` after
  merge). Break things. Tell the session what to change; the generator is one file.
- Approve the industry copy for the first industries you want to sell into. Recommend starting
  with **plumbing, HVAC, electrical, roofing, landscaping**: highest ticket, most likely to pay.

## Phase 4 — Three pilot deals (owner + agent, 2–3 weeks)
- Agent builds the first 25 Tier-A previews; human reviews the first 10.
- Emails sent by the agent from the dedicated mailbox at 10/day (warm-up), Tue–Thu mornings,
  3-touch sequence in `emails/`. Every reply is triaged: objection → same-day takedown;
  interest → human approves the pricing reply; question → agent answers from the FAQ.
- Close three. Handoff per `COMPLIANCE.md §4`: domain in the client's name, logins transferred,
  care plan or one-time invoice via Paddle (already wired on the main site).
- **Gate to Phase 5:** 3 paid deals, zero complaints, reply rate ≥ 3%, no deliverability flags.

## Phase 5 — Game time (agent, autonomous inside the guardrails)
- Weekly Routine: pull → enrich → score → build → audit → push. Daily Routine: send up to
  `max_new_contacts_per_day` (25) first touches + due follow-ups, process replies, takedowns,
  suppression list, and post a one-line summary.
- Human still gates: pricing replies, contracts, domain purchases, anything legal-sounding.
- Scale levers: raise the daily cap slowly (deliverability first), add industries, add cities,
  add a postcard channel (SOS gives a mailing address for every business; a QR code to the
  preview costs ~$0.60 each and has no CAN-SPAM footprint).

## What "transfer" means here
1. Client signs, pays. 2. Domain registered at **Namecheap** in **their** name, or registered in our
Namecheap account and pushed to their Namecheap username ("Change Ownership", free, instant, no
60-day lock) within 7 days. 3. Site rebuilt with `--mode final` (banner off, indexable, JSON-LD,
contact form), deployed to their domain on Cloudflare Pages/Netlify under an account they own.
4. Logins, source zip, and a one-page "how to change things" handed over. 5. Care plan clients get
edits through the support inbox; one-time clients get 30 days of fixes.

## Risks and how they're handled
| Risk | Handling |
|---|---|
| Owner angry a site exists | Banner + claim page + same-day takedown + never indexed |
| "You said I have no website, I do" | Emails say "couldn't find"; enrichment keeps ambiguous as unknown |
| Domain squatting accusation | Never register their name before written agreement |
| Spam complaints hurt the brand | Dedicated domain/mailbox, caps, 3-touch max, real address, instant opt-out |
| Google Places cost | ~$0.03/lookup; 2,000 leads ≈ $60; cap with `--enrich-limit` |
| Fake-looking content | No testimonials, no credential words; auditor enforces |

## Next actions
1. **You:** fill `postal_address`, pick the sending domain, decide office-Mac vs allowlist.
2. **Office Mac paste** (after `git pull` on the branch or merge to main):
   ```bash
   cd ~/lindaai-brain && git fetch origin && git checkout claude/colorado-business-websites-4j2uy7 && pip3 install -q requests && GOOGLE_MAPS_API_KEY="PASTE_KEY" bash outreach/scripts/run_pipeline.sh --enrich-limit 300 --top 25 && tail -20 outreach/reports/audit-latest.md
   ```
3. **Agent:** weekly Routine `trig_01MEGLptRWQiN9ecuH76HFWR` is scheduled (Mondays 8am Mountain, fresh session in the "Sauce Claude" environment) to run Phases 1–2 and
   report; it will tell you if the network policy still blocks it.
