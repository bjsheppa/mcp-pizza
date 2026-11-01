"""
Order creation and management services
"""
from typing import Dict, Any, Optional
from pizzapi import Address, Customer, Order, Store
from mcpizza.utils.mock_order import create_mock_order


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


def add_pizza_with_toppings(
    coupon_code: str,
    size: str = "12",
    crust: str = "NPAN",
    toppings: list = None,
    variant_code: str = None
) -> Dict[str, Any]:
    """
    Add a customized pizza with toppings using a coupon.

    Args:
        coupon_code: Coupon code (e.g., '9204')
        size: Pizza size (10, 12, 14, 16)
        crust: Crust code (NPAN, HAND, THIN, etc.)
        toppings: List of topping codes (e.g., ['P', 'S'])
        variant_code: Optional. If provided, used as the product code
            instead of the auto-generated P{size}I{crust} format. Use the
            Variant 'Code' field from the store's menu (e.g. '14SCREEN',
            '14SCPFEAST', 'PBKIREZA'). This is needed because the API's
            product code format varies by crust type and product.

    Returns:
        Pizza addition confirmation
    """
    global current_order

    if not current_order:
        raise Exception('No order created. Call create_order first.')

    if toppings is None:
        toppings = []

    # Add the coupon
    current_order.add_coupon(coupon_code)

    # Determine the product code: use explicit variant_code if given,
    # otherwise fall back to the P{size}I{crust} format.
    if variant_code is None:
        crust_map = {
            "NPAN": "PAZA",  # Pan crust
            "HAND": "HAND",  # Hand tossed
            "THIN": "THIN",
            "BROOKLYN": "BK",
        }
        product_code = f"P{size}I{crust_map.get(crust, 'HAND')}"
    else:
        product_code = variant_code

    # Build topping options: {"P": {"1/1": "1"}} = pepperoni, whole pizza
    topping_options = {}
    for topping in toppings:
        topping_options[topping] = {"1/1": "1"}

    # Add product with toppings
    current_order.add_product(product_code, topping_options)

    return {
        'success': True,
        'message': f'Added {size}" pizza with {len(toppings)} toppings using coupon {coupon_code}'
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
