# Security model

This server can spend money. These are the controls and their limits.

## Controls

| Control | What it does |
|---|---|
| Dry run by default | `place_order` only submits when `MCPIZZA_ALLOW_PLACE` is `1`/`true`/`yes`. |
| Two-step confirm | `prepare_order` returns a read-back and a random single-use `confirm_token` (10 minute TTL) bound to a hash of the order contents. Changing the order invalidates it. |
| Token-only placement | `place_order` takes only `confirm_token`. No card fields in tool arguments. |
| Card file | Card is loaded server-side from the JSON file at `MCPIZZA_CARD_FILE` (`number`, `expiry`, `cvv`, `zip`). The file must be mode 600 or 400. |
| Log redaction | Card numbers (12+ digit runs) and values under card/cvv/cvc/security/expiry/expiration/payment keys are redacted from `logs/`. Confirm tokens are not redacted. |
| Safe errors | On the order/payment path, exceptions are summarised by `mcpizza/errors.py` (`safe_error`) instead of echoing raw API text, so URLs, response bodies and order JSON never reach the model or logs. |
| Card cleared after use | The card is removed from the in-memory order after every placement attempt, success or failure. |
| Input validation | Tool parameters are validated with pydantic v2 (card type detection, quantity bounds, etc). |

## Setup checklist

- Keep the card file outside the repo and `chmod 600`.
- Do not set `MCPIZZA_ALLOW_PLACE` in shared or default configs; set it only for the session where you want a real order.
- Always show the `prepare_order` read-back to a human and get a clear yes before `place_order`.
- Keep `logs/` private.

## What this does not protect against

- **A hostile or compromised agent.** The token is returned to whoever calls `prepare_order`, so that caller can also call `place_order`. It prevents accidents, not malice. A stronger design would use a code that only the human receives out of band.
- **Anyone who can read the card file or the server's environment.**
- **Domino's side behaviour.** The API is unofficial, may change, and may require CAPTCHA.

## Reporting

Open an issue on the repo. Do not post card data or addresses in issues.
