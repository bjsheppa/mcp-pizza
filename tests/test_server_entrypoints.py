"""
Server entrypoint tests: verify tools/list and tools/call work through the MCP server.
"""
import types
from unittest import mock

import pytest

from mcpizza import server
from mcpizza.services import order_service
from mcpizza.api.client import api_client


async def test_server_list_tools_include_prepare_order():
    """tools/list should include prepare_order."""
    result = await server.list_tools(None, None)
    tools = {t.name: t for t in result.tools}
    assert "prepare_order" in tools
    assert "place_order" in tools


async def test_place_order_schema_no_card_fields():
    """place_order input schema should not contain card fields."""
    result = await server.list_tools(None, None)
    place_tool = next(t for t in result.tools if t.name == "place_order")
    schema = place_tool.input_schema
    props = schema.get("properties", {})
    card_keys = {"card_number", "card_expiry", "card_cvv", "card_zip"}
    assert not card_keys & props.keys()


async def test_prepare_order_returns_token_and_dry_run():
    """prepare_order returns a token; place_order returns DRY RUN message."""
    order = types.SimpleNamespace(
        store=types.SimpleNamespace(id="7285"),
        customer=types.SimpleNamespace(first_name="A", last_name="B", email="a@b.co", phone="8435550100"),
        data={"Products": [{"Code": "14SCREEN", "Qty": 1}], "Coupons": [], "Address": {"Street": "x"}, "Amounts": {}, "ServiceMethod": "Delivery"}
    )
    order_service.current_order = order

    with mock.patch.object(api_client, "price_order", return_value={"Status": 1, "Order": {"Amounts": {"Customer": 21.07}}}):
        r = await server.call_tool(None, types.SimpleNamespace(name="prepare_order", arguments={}))
        assert r.content[0].type == "text"
        txt = r.content[0].text
        assert "Confirm Token:" in txt

        # Extract token and place order (dry-run by default)
        tok = [l.split(": ", 1)[1] for l in txt.splitlines() if "Confirm Token" in l][0].strip()
        r2 = await server.call_tool(None, types.SimpleNamespace(name="place_order", arguments={"confirm_token": tok}))
        assert r2.content[0].type == "text"
        assert "DRY RUN" in r2.content[0].text

        # Reuse should be refused
        r3 = await server.call_tool(None, types.SimpleNamespace(name="place_order", arguments={"confirm_token": tok}))
        assert "invalid" in r3.content[0].text.lower() or "refused" in r3.content[0].text.lower()


async def test_list_tools_returns_13_tools_with_input_schema():
    """list_tools returns all 13 tools, each with an input schema."""
    result = await server.list_tools(None, None)
    assert len(result.tools) == 13
    for tool in result.tools:
        assert tool.input_schema is not None
    expected_tool_names = [
        "find_stores", "get_store_info", "get_menu", "search_menu",
        "create_order", "add_item_to_order", "add_pizza_with_toppings",
        "view_order", "clear_order", "get_coupons",
        "get_ordering_guidance", "place_order", "prepare_order"
    ]
    actual_names = {t.name for t in result.tools}
    assert set(expected_tool_names) == actual_names


async def test_call_tool_unknown_tool_returns_error():
    """An unknown tool name yields an error result."""
    r = await server.call_tool(None, types.SimpleNamespace(name="nonexistent_tool", arguments={}))
    assert r.is_error is True
    assert "Unknown tool: nonexistent_tool" in r.content[0].text


async def test_call_tool_handler_raise_returns_is_error():
    """A raising handler yields is_error=True with a redacted message, not the raw exception text."""
    secret = "card=4111111111111111 body=<secret>"

    async def boom():
        raise RuntimeError(secret)

    with mock.patch.object(server, "handle_view_order", boom):
        r = await server.call_tool(None, types.SimpleNamespace(name="view_order", arguments=None))
    assert r.is_error is True
    text = r.content[0].text
    assert "unexpected RuntimeError" in text
    assert secret not in text and "4111" not in text


async def test_call_tool_arguments_none_works_view_order():
    """arguments=None (allowed by the protocol) is treated as no arguments."""
    r = await server.call_tool(None, types.SimpleNamespace(name="view_order", arguments=None))
    assert r.content[0].type == "text"