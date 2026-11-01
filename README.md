# 🍕 MCPizza (bjsheppa fork)

An MCP (Model Context Protocol) server that lets an AI assistant browse Domino's menus, price carts, and (when explicitly enabled) place an order, via the unofficial Domino's API.

> **⚠️ Status: experimental.** Placing an order is a **dry run by default**. Live placement against Domino's has **not been verified end to end** and may hit a CAPTCHA. See [Limitations](#limitations) and [docs/SECURITY.md](docs/SECURITY.md).

## Lineage

- Original: [GrahamMcBain/mcpizza](https://github.com/GrahamMcBain/mcpizza) (MIT)
- Enhanced: [dshanklin-bv/mcp-pizza](https://github.com/dshanklin-bv/mcp-pizza) (real API calls, `add_pizza_with_toppings`, coupon tools, interaction logging)
- This fork: [bjsheppa/mcp-pizza](https://github.com/bjsheppa/mcp-pizza), hardened for real ordering

### What this fork changes

- **Menu prices fixed.** Prices come from the menu's `Variants`; `Products` always have `Price: null`.
- **Variant codes resolved from the menu.** `add_pizza_with_toppings` looks up the real Variant code (e.g. `14SCREEN`) by size and crust, or you can pass `variant_code`. If it cannot find exactly one match it returns an error listing options and leaves the order unchanged.
- **Two-step placement.** `prepare_order` returns a read-back and a single-use confirm token; `place_order` accepts only that token.
- **Card stays server-side.** It is read from a locked-down JSON file and never passes through tool arguments or the model.
- **Dry run by default.** Real placement needs `MCPIZZA_ALLOW_PLACE=1`.
- **Log redaction** of card numbers, CVVs, and expiry values.
- **Input validation** (pydantic v2) and the MCP SDK pinned to 1.x (`mcp>=1.2,<2`).

## Tools (13)

**Store and menu:** `find_stores`, `get_store_info`, `get_menu`, `search_menu`, `get_coupons`

**Ordering:** `create_order`, `add_pizza_with_toppings`, `add_item_to_order`, `view_order`, `clear_order`, `prepare_order`, `place_order`

**Guidance:** `get_ordering_guidance`

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/bjsheppa/mcp-pizza.git
cd mcp-pizza
python -m venv .venv && .venv/bin/pip install -e . pytest pytest-asyncio
```

### Claude Desktop / any MCP client

```json
{
  "mcpServers": {
    "pizza": {
      "command": "/path/to/mcp-pizza/.venv/bin/python",
      "args": ["-m", "mcpizza"],
      "env": { "MCPIZZA_CARD_FILE": "/secure/path/card.json" }
    }
  }
}
```

See `claude_desktop_config.example.json`.

### Enabling real placement (opt-in)

1. Create a JSON card file with keys `number`, `expiry`, `cvv`, `zip` and `chmod 600` it. The server refuses a group/world-readable file.
2. Set `MCPIZZA_CARD_FILE` to its path.
3. Set `MCPIZZA_ALLOW_PLACE=1` in the server environment, only when you mean it.

Without step 3, `place_order` validates everything and reports what it would send, without submitting.

## Usage

The full flow is in [WORKFLOW.md](WORKFLOW.md). In short:

1. `find_stores`, then `get_coupons` / `get_menu` for the store
2. `create_order`, then `add_pizza_with_toppings` (pass `variant_code` from the menu)
3. `view_order` to check pricing
4. `prepare_order` returns a read-back and `confirm_token`; show it to the human
5. `place_order` with only the `confirm_token`

## Layout

```
mcpizza/
  server.py            MCP server, tool registration
  logger.py            JSON interaction log with redaction
  models/params.py     pydantic v2 parameter models
  services/            store, order, payment, guidance logic
  tools/               MCP tool handlers
  api/                 Domino's HTTP client
  utils/mock_order.py  order object used with pizzapi calls
tests/                 46 tests (models, services, API client, confirm gate, card file, redaction, server entrypoints)
docs/SECURITY.md       threat model and safe-ordering setup
WORKFLOW.md            step-by-step tool workflow
docs/                 security model, pricing investigation notes
```

Logs go to `logs/interactions_YYYYMMDD.log` (gitignored), one JSON object per line.

## Tests

```bash
.venv/bin/pytest -q    # 46 passed
```

Tests do not place orders or need network access to Domino's.

## Limitations

- **CAPTCHA (unconfirmed).** Domino's may require `recaptchaVerificationRequired` on placement, per the upstream pizzapi README. Not yet confirmed here. Do not attempt to bypass it.
- **Not verified:** a live order end to end; pay-at-door / in-store payment; saved-card or account login.
- **pizzapi** is an unofficial wrapper, last released in 2019 (upstream now [ggrammar/pizzapi](https://github.com/ggrammar/pizzapi)).
- **The confirm token guards against mistakes, not a hostile agent.** Anything that can call `prepare_order` can call `place_order`.
- **MCP 2.x** is not supported yet; a port is planned as a separate change.

## Disclaimer

Unofficial and not affiliated with Domino's. Ordering through an unofficial API may violate their terms. Use at your own risk.

## License

See [CONTRIBUTING.md](CONTRIBUTING.md): no personal info in this repo.

MIT, see [LICENSE](LICENSE). Based on [GrahamMcBain/mcpizza](https://github.com/GrahamMcBain/mcpizza) (MIT).
