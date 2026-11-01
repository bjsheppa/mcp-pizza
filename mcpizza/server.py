#!/usr/bin/env python3
"""
MCPizza MCP Server
AI-Powered Pizza Ordering with Model Context Protocol

This is the main server coordinator that registers and routes MCP tools.
Business logic is in services/, tool handlers in tools/.
"""

from mcp.server import Server
from mcp.server.context import ServerRequestContext
from mcp.types import (
    Tool,
    TextContent,
    ListToolsResult,
    CallToolResult,
    CallToolRequestParams,
    PaginatedRequestParams,
)

from mcpizza.logger import interaction_logger
from mcpizza.errors import safe_error
from mcpizza.models.params import (
    StoreSearchParams,
    StoreInfoParams,
    MenuSearchParams,
    CreateOrderParams,
    AddItemParams,
    AddPizzaParams
)
from mcpizza.tools.store_tools import (
    handle_find_stores,
    handle_get_store_info
)
from mcpizza.tools.menu_tools import (
    handle_get_menu,
    handle_search_menu,
    handle_get_coupons
)
from mcpizza.tools.order_tools import (
    handle_create_order,
    handle_add_item_to_order,
    handle_add_pizza_with_toppings,
    handle_view_order,
    handle_clear_order,
    handle_place_order,
    handle_prepare_order
)
from mcpizza.tools.guidance_tools import handle_get_ordering_guidance


async def list_tools(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None = None,
) -> ListToolsResult:
    """List all available pizza ordering tools"""
    interaction_logger.log_tool_list_request()
    tools = [
        Tool(
            name="find_stores",
            description="Find nearby Domino's stores by address or zip code. Returns store IDs, addresses, and phone numbers.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Address or zip code to search for stores"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_store_info",
            description="Get detailed information about a specific Domino's store including hours and services.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Store ID to get information for"
                    }
                },
                "required": ["store_id"]
            }
        ),
        Tool(
            name="get_menu",
            description="Get the full menu for a specific store. Returns all available items organized by category.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Store ID to get menu for"
                    }
                },
                "required": ["store_id"]
            }
        ),
        Tool(
            name="search_menu",
            description="Search for specific menu items at a store. Can filter by category and search term.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Store ID to search menu for"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (optional)"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category filter: Pizza, Wings, Sides, Drinks, Desserts, etc."
                    }
                },
                "required": ["store_id"]
            }
        ),
        Tool(
            name="create_order",
            description="Create a new order for delivery or carryout. Required before adding items.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {"type": "string", "description": "Store ID"},
                    "customer_name": {"type": "string", "description": "Customer full name"},
                    "customer_email": {"type": "string", "description": "Customer email"},
                    "customer_phone": {"type": "string", "description": "Customer phone number"},
                    "delivery_address": {"type": "string", "description": "Street address"},
                    "delivery_city": {"type": "string", "description": "City"},
                    "delivery_state": {"type": "string", "description": "State (2-letter code)"},
                    "delivery_zip": {"type": "string", "description": "Zip code"},
                    "order_type": {"type": "string", "description": "Delivery or Carryout", "default": "Delivery"}
                },
                "required": ["store_id", "customer_name", "customer_email", "customer_phone",
                           "delivery_address", "delivery_city", "delivery_state", "delivery_zip"]
            }
        ),
        Tool(
            name="add_item_to_order",
            description="Add a menu item to the current order. Must create an order first.",
            input_schema={
                "type": "object",
                "properties": {
                    "item_code": {
                        "type": "string",
                        "description": "Menu item code from the menu"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Quantity to add",
                        "default": 1
                    },
                    "options": {
                        "type": "object",
                        "description": "Item customization options"
                    }
                },
                "required": ["item_code"]
            }
        ),
        Tool(
            name="add_pizza_with_toppings",
            description="Add a customized pizza with toppings using a coupon code. Handles proper product + topping configuration.",
            input_schema={
                "type": "object",
                "properties": {
                    "coupon_code": {
                        "type": "string",
                        "description": "Coupon code (e.g., '9204')"
                    },
                    "size": {
                        "type": "string",
                        "description": "Pizza size code: 10, 12, 14, or 16",
                        "default": "12"
                    },
                    "crust": {
                        "type": "string",
                        "description": "Crust code: NPAN (pan), HAND (hand tossed), THIN, BROOKLYN, etc.",
                        "default": "NPAN"
                    },
                    "toppings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topping codes: P (pepperoni), S (sausage), M (mushrooms), O (onions), etc."
                    }
                },
                "required": ["coupon_code", "toppings"]
            }
        ),
        Tool(
            name="view_order",
            description="View the current order including all items, prices, and totals.",
            input_schema={"type": "object", "properties": {}}
        ),
        Tool(
            name="clear_order",
            description="Clear the current order and start over.",
            input_schema={"type": "object", "properties": {}}
        ),
        Tool(
            name="get_coupons",
            description="Get available coupons and deals for a store. Returns coupon codes, descriptions, and prices.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Store ID to get coupons for"
                    }
                },
                "required": ["store_id"]
            }
        ),
        Tool(
            name="get_ordering_guidance",
            description="Get AI guidance on how to build the best order based on user preferences. Analyzes deals, suggests optimal pizza counts, and provides ordering strategy.",
            input_schema={
                "type": "object",
                "properties": {
                    "store_id": {
                        "type": "string",
                        "description": "Store ID to analyze deals for"
                    },
                    "user_request": {
                        "type": "string",
                        "description": "What the user wants (e.g., 'deep dish sausage and pepperoni', '2 large pizzas for a party')"
                    }
                },
                "required": ["store_id", "user_request"]
            }
        ),
        Tool(
            name="place_order",
            description="⚠️ Places a REAL order with real payment! Submit the current order to Domino's. Requires MCPIZZA_CARD_FILE env var and a confirm_token from prepare_order. In dry-run mode (default, unless MCPIZZA_ALLOW_PLACE=1): validates everything and returns \"DRY RUN: would place order for $X\" without calling api_client.place_order. In live mode (MCPIZZA_ALLOW_PLACE=1): places the actual order via Domino's API.",
            input_schema={
                "type": "object",
                "properties": {
                    "confirm_token": {"type": "string", "description": "Confirm token from prepare_order"}
                },
                "required": ["confirm_token"]
            }
        ),
        Tool(
            name="prepare_order",
            description="Price the current order and return a human-readable read-back plus a single-use confirm_token. Token expires in 10 minutes and is bound to the order contents so any change invalidates it. Must obtain a token before placing an order. Dry-run mode by default.",
            input_schema={"type": "object", "properties": {}}
        )
    ]
    return ListToolsResult(tools=tools)


async def call_tool(
    ctx: ServerRequestContext,
    params: CallToolRequestParams,
) -> CallToolResult:
    """Route tool calls to their handlers"""
    name = params.name
    arguments = params.arguments or {}
    interaction_logger.log_tool_call(name, arguments)

    try:
        # Route to appropriate handler
        if name == "find_stores":
            result = await handle_find_stores(StoreSearchParams(**arguments))
        elif name == "get_store_info":
            result = await handle_get_store_info(StoreInfoParams(**arguments))
        elif name == "get_menu":
            result = await handle_get_menu(StoreInfoParams(**arguments))
        elif name == "search_menu":
            result = await handle_search_menu(MenuSearchParams(**arguments))
        elif name == "create_order":
            result = await handle_create_order(CreateOrderParams(**arguments))
        elif name == "add_item_to_order":
            result = await handle_add_item_to_order(AddItemParams(**arguments))
        elif name == "add_pizza_with_toppings":
            result = await handle_add_pizza_with_toppings(AddPizzaParams(**arguments))
        elif name == "view_order":
            result = await handle_view_order()
        elif name == "clear_order":
            result = await handle_clear_order()
        elif name == "get_coupons":
            result = await handle_get_coupons(StoreInfoParams(**arguments))
        elif name == "get_ordering_guidance":
            result = await handle_get_ordering_guidance(
                arguments['store_id'],
                arguments['user_request']
            )
        elif name == "place_order":
            result = await handle_place_order(arguments)
        elif name == "prepare_order":
            result = await handle_prepare_order()
        else:
            interaction_logger.log_tool_response(name, False, None, error=f"Unknown tool: {name}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                is_error=True,
            )

        interaction_logger.log_tool_response(name, True, result)
        return CallToolResult(content=result, is_error=False)

    except Exception as e:
        error_msg = f"Error executing {name}: {safe_error(e)}"
        interaction_logger.log_tool_response(name, False, None, error=error_msg)
        interaction_logger.log_error("tool_execution", error_msg, {"tool": name, "arguments": arguments})
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            is_error=True,
        )


app = Server("mcpizza", on_list_tools=list_tools, on_call_tool=call_tool)


async def main():
    """Run the MCP server"""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
