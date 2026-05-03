# Beta ROI Flow

The marketing → activation → monetization sequence for the Anointed beta launch. Designed around the real cost numbers from the Kling calibration (see [pricing_calibration memory pad](../C:/Users/Owner/.claude/projects/c--Users-Owner-repos-aibiblegospelmaster/memory/pricing_calibration.md)) so the unit economics actually work.

**Principle:** give value *before* asking for money, and keep the conversion window short so the lead doesn't go cold.

---

## The 5-step flow

### 1. Capture — landing page → Supabase waitlist (✓ live)
- Hero CTA on anointed.app
- Email lands in `public.waitlist` table
- Admin gets a Resend notification at `aibiblegospels444@gmail.com`

### 2. Instant confirmation (~5 min after signup) — *not built yet*
- Send to the signer: "You're in. Watch this 60-sec sample we made from Genesis 1."
- Embed/link a YouTube clip from the channel
- **This is the biggest single ROI lever** — zero cost, sets the wow factor immediately, weeds out tire-kickers
- Requires: Resend domain verification on `anointed.app`, then a second `_send_to_signer()` call in `app.py`

### 3. Day 2 — social proof email
- "Here's what the first beta testers built" + 2 sample videos
- Builds trust without asking for anything
- Requires: a small drip scheduler (cron on Modal, or just send manually for the first batch)

### 4. Day 4 — invite
- "Your private link is ready. You get 1 free chapter render — pick any book."
- Unique invite link → sets `invited_at` in `public.waitlist`
- **Cap at 1 chapter** so cost stays bounded (~$26 for v1.6 per calibration)

### 5. Post-render — monetize
- Once they download their free video: "Want to do Romans next? Top up $25 → 1 chapter, $50 → 3 chapters."
- Stripe payment link in the email — no Stripe checkout flow needed yet
- Tracks revenue per cohort

---

## Why this works for *Anointed's* unit economics

Real cost from last session's calibration: **~$26/chapter on v1.6** (FLUX + Kling + JSON2Video + ElevenLabs).

| Step | Cost to us | Why it's worth it |
|---|---|---|
| Free chapter in step 4 | $26 (CAC) | Buys a customer who has now seen the wow factor and downloaded a real artifact |
| First $25 paid chapter | $0 net | Breakeven on CAC |
| Second $25 paid chapter | +$25 profit | Real margin starts |

**Avoid:** giving away v3.0+ tier renders for free. Those are $45+ all-in and the math breaks.

---

## Tooling

All of it runs on Resend alone until ~1,000 signups:
- Steps 2–4 → transactional sends from the FastAPI server
- Step 5 → Stripe payment link embedded in the email

No newsletter platform, no marketing automation tool needed yet. Add Mailchimp / ConvertKit only when the list outgrows what Resend Broadcasts can handle.

---

## Open product decisions

These need to be answered before step 4 ships:

1. **Free with caps, or paid from day 1?**
   - Option A: 1 chapter free, then $25 to continue (current draft above)
   - Option B: $25 entry from the invite — no free chapter, but lower CAC
   - Option C: $5 entry to weed out tire-kickers, redeemable as credit

2. **How many slots per week?**
   - Limits help with quality control + create urgency in the social proof email
   - Suggest: 25/week for the first month → tune from there

3. **Which Kling tier on the free chapter?**
   - v1.6 = $26 cost (cheapest, lowest motion quality)
   - v2.1 = also ~$26 but better motion (preferred)
   - Anything higher = unprofitable as a giveaway

---

## Build order

1. ✓ Waitlist table + signup endpoint
2. ⏳ **Verify `anointed.app` in Resend** (in progress — DNS records being added)
3. Add signer confirmation email (step 2 of the flow)
4. Pick the free-tier model + chapter cap (open decision #1, #3 above)
5. Build the invite link + `invited_at` flow
6. Wire Stripe payment link
7. Day-2 drip email (manual at first, cron later)
