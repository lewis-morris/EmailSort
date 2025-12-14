# Email Triage Agent Specification

This document mirrors the behaviour described in the system prompt and can be
used as human‑readable documentation or plugged into a higher‑level agent.

## Categories

Use these categories exactly as spelled:

- **Urgent** - needs doing right away, highly time sensitive.
- **Priority 1** - important and should be handled today.
- **Priority 2** - important but can be handled later this week.
- **Priority 3** - open ended completion date, low urgency.
- **Marketing** - newsletters, promotions, marketing blasts, etc.
- **Informational** - information worth reading but that does not clearly
  require action.
- **No reply needed** - might be worth a skim; at most a short acknowledgement.
- **Complete** - conversation and work are clearly finished.
- **Possibly Complete** - seems finished but uncertain; user should review.
- **Processed** - synthetic tag added by the tool to avoid reprocessing.
- **Payment Request** - sender is asking for payment to be made.
- **Invoice** - an invoice is provided for records/payment.
- **Order Confirmation** - confirmation of an order we placed.
- **Issue** - a problem is reported that needs attention.
- **Task** - someone is asking for a task to be completed.

## Flags

- **Today** - must be handled today.
- **Tomorrow** - should be handled tomorrow.
- **This week** - sometime this week.
- **Next week** - can wait until next week.
- **No date** - no specific due date.
- **Mark as complete** - marks follow-up as completed.

## Behaviour

- Every processed message gets the `Processed` category.
- Only mark `Complete` when very confident; otherwise prefer `Possibly Complete`.
- Marketing is usually low priority and may be marked read.
- Informational stays unread but gets summarised for daily digests.
- Messages needing a response or action are kept unread and flagged.
- Draft replies must be concise, clear, and in the user's voice.
