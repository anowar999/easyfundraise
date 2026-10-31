# ADR-004: Sending, the agent and the data room

**Status:** accepted · 2026-10-31

- **Gmail is the only sender.** Emails go from the founder's own mailbox via the Gmail API (`gmail.send`,
  `gmail.readonly`, asked only when they first connect). Refresh tokens are AES-256-GCM encrypted with
  `EF_TOKEN_KEY`. A revoked token marks the mailbox disconnected and pauses sending, with a notification.
- **Send safety lives in the worker, not the UI.** Every send re-checks: exclusion list, role addresses, the
  daily cap in the user's timezone with a 10-day warm-up from 5/day, at most 3 a day per recipient domain, and
  45–180 s pacing. Follow-ups thread on the original Message-ID and stop on any reply.
- **Replies are polled**, using Gmail history with a thread scan as fallback (idempotent per message id).
  Pub/Sub push is a later optimisation; polling every ~5 minutes is enough for founder workflows.
- **Opens are a hint.** The pixel ignores fetches in the first 30 s (scanners) and counts proxy prefetches once.
  Founders can turn tracking off per workspace.
- **Claude is optional and bounded.** Drafting, chat, briefs and polish call Claude through the official SDK with
  JSON-schema output. Drafts may only cite numbered facts we stored; anything else fails validation and the
  template engine is used instead. Each workspace has a monthly token budget per plan. Chat proposes changes
  (move stage, add note, draft sequence) that the founder applies with a tap; it never sends email.
- **Round updates only name backers the founder marked "OK to name".** The server rejects anything else.
- **Data room documents are stored in Postgres** (≤20 MB each) to keep one datastore; move to S3 when volume
  needs it. Personal links set a signed cookie and the token is removed from the address bar. Rooms are
  noindex unless the founder opts in and the room is public.
- **Billing** uses Stripe Checkout and the customer portal over plain HTTPS (no SDK); webhooks are verified with
  the signing secret and set the workspace tier.
