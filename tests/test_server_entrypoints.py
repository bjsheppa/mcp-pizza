"""
Server entrypoint tests: verify tools/list and tools/call work through the MCP server.
"""
import asyncio
import json
import types
from unittest import mock

import pytest

from mcpizza import server
from mcpizza.services import order_service
from mcpizza.api.client import api_client


async def test_server_list_tools_include_prepare_order():
    """tools/list should include prepare_order."""
    tools = {t.name: t for t in await server.list_tools()}
    assert "prepare_order" in tools
    assert "place_order" in tools


async def test_place_order_schema_no_card_fields():
    """place_order inputSchema should not contain card fields."""
    tools = {t.name: t for t in await server.list_tools()}
    schema = tools["place_order"].inputSchema
    props = schema.get("properties", {})
    card_keys = {"card_number", "card_expiry", "card_cvv", "card_zip"}
    assert not card_keys & props.keys()


async def test_prepare_order_returns_token_and_dry_run():
    """prepare_order returns a token; place_order returns DRY RUN message."""
    tools = {t.name: t for t in await server.list_tools()}

    order = types.SimpleNamespace(
        store=types.SimpleNamespace(id="7285"),
        customer=types.SimpleNamespace(first_name="A", last_name="B", email="a@b.co", phone="8435550100"),
        data={"Products": [{"Code": "14SCREEN", "Qty": 1}], "Coupons": [], "Address": {"Street": "x"}, "Amounts": {}, "ServiceMethod": "Delivery"}
    )
    order_service.current_order = order

    with mock.patch.object(api_client, "price_order", return_value={"Status": 1, "Order": {"Amounts": {"Customer": 21.07}}}):
        # Call prepare_order via server
        r = await server.call_tool("prepare_order", {})
        assert r[0].type == "text"
        txt = r[0].text
        assert "Confirm Token:" in txt

        # Extract token and place order (dry-run by default)
        tok = [l.split(": ", 1)[1] for l in txt.splitlines() if "Confirm Token" in l][0].strip()
        r2 = await server.call_tool("place_order", {"confirm_token": tok})
        assert r2[0].type == "text"
        assert "DRY RUN" in r2[0].text

        # Reuse should be refused
        r3 = await server.call_tool("place_order", {"confirm_token": tok})
        assert "invalid" in r3[0].text.lower() or "refused" in r3[0].text.lower()