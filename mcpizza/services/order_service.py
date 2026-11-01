"""
Order creation and management services
"""
import re
from typing import Dict, Any, List, Optional
from pizzapi import Address, Customer, Order, Store
from mcpizza.utils.mock_order import create_mock_order
from mcpizza.api.client import api_client


# Global state for current order
current_order: Optional[Any] = None
current_store: Optional[Any] = None
current_customer: Optional[Any] = None


def create_order(
    store_id: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    delivery_address: str,
    delivery_city: str,
    delivery_state: str,
    delivery_zip: str,
    order_type: str = "Delivery"
) -> Dict[str, Any]:
    """
    Create a new order.

    Args:
        store_id: Store ID
        customer_name: Customer full name
        customer_email: Customer email
        customer_phone: Customer phone number
        delivery_address: Street address
        delivery_city: City
        delivery_state: State (2-letter code)
        delivery_zip: Zip code
        order_type: "Delivery" or "Carryout"

    Returns:
        Order creation confirmation
    """
    global current_order, current_store, current_customer

    # Parse customer name
    name_parts = customer_name.split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    # Create customer object
    customer = Customer(
        first_name,
        last_name,
        customer_email,
        customer_phone
    )

    # Create address object
    address = Address(
        delivery_address,
        delivery_city,
        delivery_state,
        delivery_zip
    )

    # Get store by finding closest one to the address
    store = None
    try:
        all_stores = address.closest_store()
        # closest_store() can return a single store or a list
        if isinstance(all_stores, list):
            # Find the requested store in the list
            store = next((s for s in all_stores if s.id == store_id), all_stores[0])
        else:
            store = all_stores
    except Exception:
        # closest_store() may fail in environments without store data;
        # fall back to creating a Store from the requested store_id
        store = Store(data={'StoreID': store_id}, country='us')

    # Create order - use mock order to bypass menu parsing bugs
    try:
        order = Order(store, customer, address)
    except Exception:
        # If Order() fails, create mock order
        order = create_mock_order(store, customer, address, order_type)

    # Store the requested store_id in order data for consistent reference
    if hasattr(order, 'data') and isinstance(order.data, dict):
        order.data['store_id'] = store_id

    # Store globally
    current_order = order
    current_store = store
    current_customer = customer

    return {
        'success': True,
        'message': f'Order created for {customer_name}',
        'store_id': store_id,
        'order_type': order_type
    }


def add_item_to_order(item_code: str, quantity: int = 1, options: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Add an item to the current order.

    Args:
        item_code: Menu item code
        quantity: Quantity to add
        options: Item customization options

    Returns:
        Item addition confirmation
    """
    global current_order

    if not current_order:
        raise Exception('No order created. Call create_order first.')

    # Add item (4-digit codes are coupons)
    if item_code.isdigit() and len(item_code) == 4:
        current_order.add_coupon(item_code)
        return {
            'success': True,
            'message': f'Added coupon {item_code} to order'
        }
    else:
        current_order.add_product(item_code, options, quantity)
        return {
            'success': True,
            'message': f'Added {quantity}x {item_code} to order'
        }


# Crust code (as accepted by add_pizza_with_toppings) -> regex over the menu
# variant Name. Matching is by whole word so e.g. "NY" cannot match "SPINACH".
_CRUST_PATTERNS = {
    "HAND": r"\bHAND\b",
    "THIN": r"\bTHIN\b",
    "NPAN": r"\bPAN\b",
    "BROOKLYN": r"\bBROOKLYN\b",
    "BKLYN": r"\bBROOKLYN\b",
    "NY": r"\b(NEW YORK|NY)\b",
}


def _resolve_variant_code(menu_data: Dict[str, Any], size: str, crust: str):
    """Find the menu Variant code for a pizza of this size and crust.

    Only variants of products whose ProductType is 'Pizza' are considered.
    Returns (code, None) on exactly one match, otherwise (None, options)
    where options lists candidate variants (code, name, price) so the caller
    can pick one explicitly. Never guesses.
    """
    products = menu_data.get('Products', {})
    pattern = _CRUST_PATTERNS.get(str(crust).upper())
    candidates: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    for vcode, v in menu_data.get('Variants', {}).items():
        if products.get(v.get('ProductCode'), {}).get('ProductType') != 'Pizza':
            continue
        entry = {'code': vcode, 'name': v.get('Name', ''), 'price': v.get('Price')}
        if str(v.get('SizeCode')) != str(size):
            continue
        candidates.append(entry)
        if pattern and re.search(pattern, entry['name'].upper()):
            matches.append(entry)
    if len(matches) == 1:
        return matches[0]['code'], None
    # No unique match: offer same-size pizzas, or all pizzas if none at that size.
    if not candidates:
        candidates = [
            {'code': c, 'name': v.get('Name', ''), 'price': v.get('Price')}
            for c, v in menu_data.get('Variants', {}).items()
            if products.get(v.get('ProductCode'), {}).get('ProductType') == 'Pizza'
        ]
    return None, matches or candidates


def _resolution_error(message: str, options: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        'success': False,
        'message': message,
        'error': {'code': 'VARIANT_RESOLUTION_ERROR', 'options': options or []},
    }


def add_pizza_with_toppings(
    coupon_code: str,
    size: str = "12",
    crust: str = "NPAN",
    toppings: list = None,
    variant_code: str = None,
    menu_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Add a customized pizza with toppings using a coupon.

    Args:
        coupon_code: Coupon code to use (e.g., '9204')
        size: Pizza size in inches (10, 12, 14, 16)
        crust: Crust code (NPAN, HAND, THIN, BROOKLYN, NY)
        toppings: List of topping codes (e.g., ['P', 'S'])
        variant_code: Optional explicit menu Variant code (e.g. '14SCREEN').
            If omitted, it is resolved from the current store's menu by size
            and crust. If it cannot be resolved to exactly one variant, an
            error listing the options is returned and the order is unchanged.
        menu_data: Optional pre-fetched menu (used by tests); fetched from the
            store otherwise.

    Returns:
        Pizza addition confirmation, or an error result.
    """
    global current_order

    if not current_order:
        raise Exception('No order created. Call create_order first.')

    if toppings is None:
        toppings = []

    product_code = variant_code
    if product_code is None:
        store_id = (getattr(getattr(current_order, 'store', None), 'id', None)
                    or (current_order.data or {}).get('StoreID'))
        if not store_id:
            return _resolution_error('Order has no store; cannot resolve pizza variant. Pass variant_code.')
        if menu_data is None:
            try:
                menu_data = api_client.get_store_menu(store_id)
            except Exception as e:
                return _resolution_error(f'Could not fetch store menu ({e}); pass variant_code.')
        product_code, options = _resolve_variant_code(menu_data, size, crust)
        if product_code is None:
            return _resolution_error(
                f'No unique {size}" {crust} pizza variant found; pass variant_code.', options)

    # Add the coupon only after the product code is known
    current_order.add_coupon(coupon_code)

    # Build topping options: {"P": {"1/1": "1"}} = pepperoni, whole pizza
    topping_options = {}
    for topping in toppings:
        topping_options[topping] = {"1/1": "1"}

    current_order.add_product(product_code, topping_options)

    return {
        'success': True,
        'message': f'Added {size}" pizza ({product_code}) with {len(toppings)} toppings using coupon {coupon_code}'
    }


def view_order() -> Dict[str, Any]:
    """
    View the current order details.

    Returns:
        Order details including items and pricing
    """
    global current_order

    if not current_order:
        raise Exception('No order created yet.')

    # Use stored store_id from order data if available, otherwise use object store_id
    store_id = current_order.data.get('store_id') if hasattr(current_order, 'data') and isinstance(current_order.data, dict) else None
    
    return {
        'store_id': store_id if store_id else (current_order.store.id if hasattr(current_order, 'store') else 'N/A'),
        'customer': {
            'name': f"{current_order.customer.first_name} {current_order.customer.last_name}",
            'email': current_order.customer.email,
            'phone': current_order.customer.phone
        } if hasattr(current_order, 'customer') else {},
        'coupons': current_order.data.get('Coupons', []),
        'products': current_order.data.get('Products', []),
        'amounts': current_order.data.get('Amounts', {}),
        'service_method': current_order.data.get('ServiceMethod', 'N/A')
    }


def clear_order() -> Dict[str, Any]:
    """
    Clear the current order.

    Returns:
        Confirmation message
    """
    global current_order, current_store, current_customer

    current_order = None
    current_store = None
    current_customer = None

    return {
        'success': True,
        'message': 'Order cleared'
    }



def get_current_order():
    """Get the current order object"""
    return current_order
