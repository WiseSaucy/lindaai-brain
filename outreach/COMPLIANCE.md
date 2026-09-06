# Compliance rulebook — Colorado preview-site outreach

The sending agent follows these without exception. `scripts/audit_site.py` enforces the
mechanical parts; the rest is procedure.

## 1. Email (CAN-SPAM, 15 U.S.C. §7701 et seq.)
Unsolicited commercial email to businesses is legal in the U.S. when every message:
- has an accurate From, Reply-To, and routing information (real mailbox we monitor)
- has a subject that is not misleading (no fake "Re:", no "invoice", no "urgent")
- includes our **valid physical postal address** (`studio.json → postal_address`)
- gives a clear opt-out that works for at least 30 days and is honored within 10 business
  days (we honor it same day and add the address to `leads/suppression.csv`)
- is identified as a solicitation (our sign-off and footer do this plainly)
Penalties run up to $53,088 per email, so the auditor fails any template missing an element.
Colorado has no separate commercial-email statute that adds requirements beyond CAN-SPAM.

## 2. No texting, no robocalls
The TCPA covers SMS. Do not text any lead from an automated system. Phone calls are placed by a
human only, never to numbers on the National Do Not Call list, and never before 8am or after
9pm local (Colorado's no-call rules, C.R.S. 6-1-901 et seq.).

## 3. Honesty about the preview (Colorado Consumer Protection Act, C.R.S. 6-1-105)
- Every preview page carries the banner "not been reviewed or approved by the business" and
  links to the claim/remove page. Every email says the same.
- Never state a business "has no website"; say "I couldn't find one." Enrichment can be wrong.
- No fabricated reviews, testimonials, star ratings, "licensed/insured", awards, or years in
  business. The auditor fails pages containing these words unless `verified_claims` is set in
  the lead row after the owner confirms them in writing.
- Previews are `noindex,nofollow`. They are drafts for one recipient, not public listings.
- `sitemap.xml` and JSON-LD LocalBusiness are only emitted in `--mode final`.

## 4. Domains (Anticybersquatting Consumer Protection Act, 15 U.S.C. §1125(d); UDRP)
- **Never register a domain containing a prospect's business name before they agree in
  writing.** Registering "theirbusiness.com" on spec is textbook bad-faith registration.
- Previews live under a domain we own: `lindaai-brain.com/sites/<slug>/` (or a neutral
  `previews.<ourdomain>` subdomain). Never on a look-alike domain.
- At signing, the domain is registered **in the client's name** (registrant = their business,
  their email as account owner) through a registrar that supports easy account moves
  (Cloudflare Registrar, Porkbun, Namecheap). If we must buy it first for speed, we initiate a
  registrar "push"/account change to the client within 7 days and never charge markup on it.
- Handoff = transfer of registrar account or domain push + DNS + hosting login + source zip.
  Document it in `leads/handoffs.csv`.

## 5. Takedown SLA
Any of: "remove", "stop", "unsubscribe", "not interested", "who authorized this", a lawyer's
letter, or silence after email 3 → the site directory is deleted and the change pushed the
same business day, `reply-remove.md` is sent, and the business goes on the suppression list.
Three-touch maximum. No re-adding a suppressed business in a later pull (`enrich_leads.py`
skips anything in `suppression.csv`).

## 6. Data handling
- Source data is public record (Colorado SOS) plus what businesses publish for contact.
- Store only business contact details; never scrape personal social profiles.
- `lindaai-brain` is a **public** repo. Lead CSVs, the build queue, and the suppression list are
  git-ignored and must never be committed here; keep them on the office Mac (or in the private
  `lindaai-ops` repo). Generated `sites/` are public by design; they contain only what the
  preview shows.

## 7. Human gates
- A human reviews the first 10 previews of every new industry template before any send.
- A human approves every pricing/payment email (`reply-interested.md`) before it goes out.
- A human signs every client agreement. The agent drafts; it does not contract.
