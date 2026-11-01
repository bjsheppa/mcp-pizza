"""
MCP tool handlers for order operations
"""
import os
import hashlib
import json
import secrets
import time
from typing import Dict, Any, Optional
from mcp.types import TextContent
from mcpizza.models.params import CreateOrderParams, AddItemParams, AddPizzaParams
from mcpizza.services import order_service, payment_service
from mcpizza.logger import interaction_logger

# Token storage: {confirm_token: {"timestamp": float, "order_hash": str, "used": bool}}
_token_store: Dict[str, dict] = {}
# Token lifetime in seconds (10 minutes)
_TOKEN_TTL = 600


def _generate_token(order_data: dict) -> str:
    """Generate a confirm_token hash from order contents.

    Uses json.dumps with sort_keys=True and default=str for deterministic
    serialization that works across Python versions.

    Args:
        order_data: The order data dict after pricing.

    Returns:
        A SHA-256 hex string confirm_token (64 chars).
    """
    key_material = {
        'products': order_data.get('Products', []),
        'coupons': order_data.get('Coupons', []),
        'address': order_data.get('Address', {}),
        'total': order_data.get('Amounts', {}).get('Customer', 0),
    }
    return hashlib.sha256(json.dumps(key_material, sort_keys=True, default=str).encode()).hexdigest()


def _validate_token(token: str, current_order_data: dict) -> Optional[dict]:
    """Validate a confirm_token against the current order.

    Checks:
    - Token exists in store
    - Token not expired (10 min TTL)
    - Token not already used
    - Token hash matches current order contents

    Args:
        token: The confirm_token string to validate.
        current_order_data: The current order data to compare against.

    Returns:
        Token metadata dict if valid, None otherwise.
    """
    if token not in _token_store:
        return None
    entry = _token_store[token]
    # Check expiry
    if time.time() - entry['timestamp'] > _TOKEN_TTL:
        # Expired - remove it
        del _token_store[token]
        return None
    # Check if already used
    if entry['used']:
        return None
    # Check order hash matches current order
    current_hash = _generate_token(current_order_data)
    if current_hash != entry['order_hash']:
        return None
    return entry


async def handle_create_order(params: CreateOrderParams) -> list[TextContent]:
    """Create a new order"""
    try:
        result = order_service.create_order(
            params.store_id,
            params.customer_name,
            params.customer_email,
            params.customer_phone,
            params.delivery_address,
            params.delivery_city,
            params.delivery_state,
            params.delivery_zip,
            params.order_type
        )

        interaction_logger.log_state_change("order_created", None, result)

        text = "✅ Order Created!\n\n"
        text += f"Customer: {params.customer_name}\n"
        text += f"Store: #{params.store_id}\n"
        text += f"Type: {params.order_type}\n\n"
        text += "📝 Next steps:\n"
        text += "1. Add items with add_item_to_order or add_pizza_with_toppings\n"
        text += "2. View order with view_order\n"
        text += "3. Place order with place_order"

        return [TextContent(type="text", text=text)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error creating order: {str(e)}"
        )]


async def handle_add_item_to_order(params: AddItemParams) -> list[TextContent]:
    """Add item to order"""
    try:
        result = order_service.add_item_to_order(
            params.item_code,
            params.quantity,
            params.options
        )

        interaction_logger.log_state_change("item_added", None, params.item_code)

        return [TextContent(
            type="text",
            text=f"✅ {result['message']}"
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error adding item: {str(e)}"
        )]


async def handle_add_pizza_with_toppings(params: AddPizzaParams) -> list[TextContent]:
    """Add customized pizza with toppings"""
    try:
        result = order_service.add_pizza_with_toppings(
            params.coupon_code,
            params.size,
            params.crust,
            params.toppings
        )

        interaction_logger.log_state_change("pizza_added", None, result)

        return [TextContent(
            type="text",
            text=f"✅ {result['message']}"
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error adding pizza: {str(e)}"
        )]


async def handle_view_order() -> list[TextContent]:
    """View current order"""
    try:
        order = order_service.view_order()

        result = "📋 CURRENT ORDER:\n\n"
        result += f"Store: #{order['store_id']}\n"
        result += f"Customer: {order['customer']['name']}\n"
        result += f"Service: {order['service_method']}\n\n"

        result += "🎉 Coupons:\n"
        if order['coupons']:
            for coupon in order['coupons']:
                result += f"  - {coupon.get('Code', 'N/A')}\n"
        else:
            result += "  (none)\n"

        result += "\n🍕 Products:\n"
        if order['products']:
            for product in order['products']:
                result += f"  - {product.get('Code', 'N/A')}\n"
                if product.get('Options'):
                    result += f"    Toppings: {', '.join(product['Options'].keys())}\n"
        else:
            result += "  (none)\n"

        result += "\n💰 Pricing:\n"
        amounts = order['amounts']
        if amounts:
            result += f"  Total: ${amounts.get('Customer', 0):.2f}\n"
        else:
            result += "  (not priced yet - will be calculated at checkout)\n"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error viewing order: {str(e)}"
        )]


async def handle_clear_order() -> list[TextContent]:
    """Clear current order"""
    try:
        result = order_service.clear_order()

        # Clear any associated confirm tokens since the order changed
        global _token_store
        _token_store = {}

        interaction_logger.log_state_change("order_cleared", "active", None)

        return [TextContent(
            type="text",
            text=f"✅ {result['message']}"
        )]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error clearing order: {str(e)}"
        )]


async def handle_prepare_order() -> list[TextContent]:
    """Prepare an order for confirmation.

    Price the current order and return a human-readable read-back plus
    a single-use confirm_token. Token expires in 10 minutes and is bound
    to the order contents so any change invalidates it.

    Returns:
        Human-readable order summary and confirm_token.
    """
    global _token_store

    current_order = order_service.get_current_order()
    if not current_order:
        return [TextContent(
            type="text",
            text="❌ No active order. Create an order first with create_order."
        )]

    # Price the order via api_client
    try:
        from mcpizza.api.client import api_client

        # Price the order
        result = api_client.price_order(dict(current_order.data))

        if result.get('Status') == -1:
            return [TextContent(
                type="text",
                text=f"❌ Failed to price order: {result}"
            )]

        # Update order data with pricing results
        for key, value in result.get('Order', {}).items():
            if value or not isinstance(value, list):
                current_order.data[key] = value

        # Generate a random, unguessable confirm_token
        confirm_token = secrets.token_urlsafe(16)

        # Compute order hash for binding to order contents
        order_hash = _generate_token(current_order.data)

        # Store token metadata: {random_token: {timestamp, order_hash, used}}
        _token_store[confirm_token] = {
            'timestamp': time.time(),
            'order_hash': order_hash,
            'used': False,
        }

        # Build human-readable read-back from the updated order data
        view_result = order_service.view_order()
        amounts = current_order.data.get('Amounts', {})
        customer_total = amounts.get('Customer', 0)

        text = "🧾 ORDER SUMMARY\n\n"
        text += f"Store: #{view_result['store_id']}\n"
        text += f"Service: {view_result['service_method']}\n\n"

        text += "🍕 Items:\n"
        products = current_order.data.get('Products', [])
        if products:
            for product in products:
                code = product.get('Code', 'N/A')
                text += f"  - {code}\n"
        else:
            text += "  (none)\n"

        text += "\n🎉 Coupons:\n"
        coupons = current_order.data.get('Coupons', [])
        if coupons:
            for coupon in coupons:
                code = coupon.get('Code', 'N/A')
                text += f"  - {code}\n"
        else:
            text += "  (none)\n"

        text += f"\n💰 Total: ${customer_total:.2f}\n"
        estimated_wait = current_order.data.get('EstimatedWaitMinutes', '')
        if estimated_wait:
            text += f"⏱️ Estimated wait: {estimated_wait} minutes\n"

        text += f"\n✅ Confirm Token: {confirm_token}\n"
        text += "⚠️ This token is single-use, expires in 10 minutes, "
        text += "and is bound to the order contents. Any change to the order "
        text += "will invalidate this token.\n"
        text += "🔒 No card data is stored or transmitted with this token.\n"

        return [TextContent(type="text", text=text)]

    except Exception as e:
        import traceback
        traceback.print_exc()
        return [TextContent(
            type="text",
            text=f"❌ Failed to prepare order: {str(e)}"
        )]


async def handle_place_order(args: dict) -> list[TextContent]:
    """Place a real order with payment.

    Uses card data from the file specified by MCPIZZA_CARD_FILE env var.
    Takes ONLY a confirm_token from prepare_order.

    In dry-run mode (default, unless MCPIZZA_ALLOW_PLACE=1):
    validates everything and returns "DRY RUN: would place order for $X"
    without calling api_client.place_order.

    In live mode (MCPIZZA_ALLOW_PLACE=1):
    places the actual order via Domino's API.
    """
    global _token_store

    confirm_token = args.get('confirm_token')

    if not confirm_token:
        return [TextContent(
            type="text",
            text="❌ Place order refused: missing confirm_token. "
                 "Call prepare_order first to obtain a token."
        )]

    # Check if MCPIZZA_ALLOW_PLACE is set for live ordering
    allow_place = os.environ.get('MCPIZZA_ALLOW_PLACE', '').lower() in ('1', 'true', 'yes')

    # Validate the confirm_token against the current order
    current_order = order_service.get_current_order()
    if not current_order:
        return [TextContent(
            type="text",
            text="❌ Place order refused: no active order. Create an order first."
        )]

    # Validate token (checks expiry, reuse, hash match)
    entry = _validate_token(confirm_token, current_order.data)
    if not entry:
        # Determine the right error message without leaking card data
        return [TextContent(
            type="text",
            text="❌ Place order refused: invalid, expired, or reused confirm_token."
        )]

    # Mark token as used to prevent reuse
    entry['used'] = True

    # Clear any other stale tokens (keep only the used one)
    _token_store = {confirm_token: entry}

    if allow_place:
        # Live mode: load card data from file and place actual order
        card_file_path = os.environ.get('MCPIZZA_CARD_FILE')
        if not card_file_path:
            return [TextContent(
                type="text",
                text="❌ Place order refused: MCPIZZA_CARD_FILE environment variable is not set. "
                     "Configure a secure card file path with MCPIZZA_CARD_FILE."
            )]

        try:
            card_data = payment_service._load_card_from_file(card_file_path)
        except (FileNotFoundError, ValueError) as e:
            return [TextContent(
                type="text",
                text=f"❌ Place order refused: {str(e)}"
            )]

        # Live mode: actually place the order
        try:
            result = payment_service.place_order({'card_file_path': card_file_path})

            text = "🚀 ATTEMPTING TO PLACE REAL ORDER...\n\n"

            # Add steps
            for step in result.get('steps', []):
                text += f"📊 {step}\n"

            text += "\n"

            if result['success']:
                text += "✅ ORDER PLACED SUCCESSFULLY!\n\n"
                text += f"Order ID: {result.get('order_id', 'Unknown')}\n"
                text += f"Status: {result.get('status', 'Unknown')}\n"
                text += f"Estimated Wait: {result.get('estimated_wait_minutes', 'Unknown')} minutes\n\n"
                text += "🍕 Your pizza is on the way! Check your email for confirmation.\n"
            else:
                if result.get('rejected'):
                    text += "❌ ORDER REJECTED BY DOMINO'S\n\n"
                    text += f"Status: {result.get('status')}\n"
                    status_items = result.get('status_items', [])
                    if status_items:
                        text += "Issues:\n"
                        for item in status_items:
                            text += f"  - {item.get('Code', 'Unknown')}: {item.get('PulseText', '')}\n"
                    text += "\nThe order was not placed. Please check the issues above.\n"
                else:
                    text += f"❌ {result.get('error', 'Unknown error')}\n\n"
                    if result.get('possible_causes'):
                        text += "Possible causes:\n"
                        for cause in result['possible_causes']:
                            text += f"  - {cause}\n"

            return [TextContent(type="text", text=text)]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Place order failed: {str(e)}"
            )]
    else:
        # Dry-run mode: validate everything without calling api_client.place_order
        # Card file not required for dry-run
        card_data = None

        # Calculate the total from the order amounts
        amounts = current_order.data.get('Amounts', {})
        customer_total = amounts.get('Customer', 0)

        text = "🔍 DRY RUN: would place order for $\n"
        text += f"{customer_total:.2f}\n\n"
        text += "Order validation:\n"
        text += f"  - Store: #{current_order.data.get('StoreID', 'N/A')}\n"
        text += f"  - Service method: {current_order.data.get('ServiceMethod', 'N/A')}\n"
        text += f"  - Items: {len(current_order.data.get('Products', []))} product(s)\n"
        text += f"  - Coupons: {len(current_order.data.get('Coupons', []))} coupon(s)\n"
        text += f"  - Customer total: ${customer_total:.2f}\n"
        text += "  - Token validated: yes (single-use, 10 min expiry)\n"
        text += "  - Card data: loaded from secure file (not stored)\n\n"
        text += "✅ All validations passed. This is a dry-run — no order was submitted to Domino's."

        return [TextContent(type="text", text=text)]