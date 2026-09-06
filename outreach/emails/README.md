# Outreach email sequence

Three touches, then stop. Every template is audited by `scripts/audit_site.py` for the
CAN-SPAM essentials (real postal address, working opt-out, honest subject, sender identified)
plus our own rule: the email must say the preview is **not approved by or affiliated with**
the business. The auditor fails the templates until `config/studio.json` has a real
`postal_address`.

| File | When | Purpose |
|---|---|---|
| `01-first-touch.md` | Day 0 | Link to the preview, offer to remove it |
| `02-follow-up.md` | Day 4–6, no reply | Answer the two questions everyone asks |
| `03-last-note.md` | Day 10–13, no reply | Final touch, sets a takedown date |
| `reply-interested.md` | On a positive reply | Pricing + next step (human reviews before sending) |
| `reply-remove.md` | On any objection | Confirm takedown, add to suppression list |

Variables use `{{double_braces}}`. `{{postal_address}}`, `{{contact_email}}`, `{{from_name}}`,
`{{offer_name}}` and the prices come from `config/studio.json`; the rest come from the lead row.

## Rules the sending agent must follow
1. Never send to an address the lead didn't publish for business contact.
2. Send from a dedicated mailbox on a secondary domain, never the main brand mailbox.
   SPF, DKIM and DMARC must pass before the first send.
3. Volume caps and send days are in `studio.json` → `sending`. Start at 10/day for the first
   two weeks while the mailbox warms up.
4. "remove", "stop", "unsubscribe", "not interested", or any objection = take the site down
   the same day, send `reply-remove.md`, add the address and business to `leads/suppression.csv`.
5. Never claim the business has no website. Say "I couldn't find one."
6. Positive replies go to a human before any pricing or payment link is sent.
