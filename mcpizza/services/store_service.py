"""
Store lookup and menu browsing services
"""
from typing import List, Dict, Any, Optional
from pizzapi import Address, Store
from mcpizza.api.client import api_client


def find_stores(query: str) -> List[Dict[str, Any]]:
    """
    Find nearby Domino's stores by address or zip code.

    Args:
        query: Address or zip code to search

    Returns:
        List of store dictionaries with id, address, phone, and open status
    """
    # Detect if query is a zip code (5 digits)
    if query.strip().isdigit() and len(query.strip()) == 5:
        # For zip codes, create Address with empty street/city/region
        address = Address('', '', '', query.strip())
    else:
        # For full addresses, let pizzapi parse it
        address = Address(query)

    # Find closest stores
    stores = address.closest_store()

    # Handle single store or list of stores
    if not isinstance(stores, list):
        stores = [stores]

    # Format results
    results = []
    for store in stores[:5]:  # Limit to 5 stores
        results.append({
            'id': store.id,
            'address': f"{store.data.get('AddressDescription', 'N/A')}",
            'phone': store.data.get('Phone', 'N/A'),
            'is_open': store.data.get('IsOpen', False)
        })

    return results


def get_store_info(store_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific store.

    Args:
        store_id: Store ID

    Returns:
        Store information dictionary
    """
    store_data = api_client.get_store_info(store_id)

    return {
        'id': store_data.get('StoreID'),
        'address': store_data.get('AddressDescription'),
        'phone': store_data.get('Phone'),
        'hours': store_data.get('HoursDescription'),
        'is_open': store_data.get('IsOpen'),
        'is_delivery_store': store_data.get('IsDeliveryStore'),
        'service_hours_description': store_data.get('ServiceHoursDescription', {})
    }


def get_menu(store_id: str) -> Dict[str, Any]:
    """
    Get full menu for a store.

    Args:
        store_id: Store ID

    Returns:
        Menu data organized by category
    """
    menu_data = api_client.get_store_menu(store_id)
    products = menu_data.get('Products', {})
    variants = menu_data.get('Variants', {})

    # Build a price lookup from variants: product_code -> first variant price
    product_prices = {}
    for vcode, vitem in variants.items():
        pc = vitem.get('ProductCode')
        if pc and pc not in product_prices:
            product_prices[pc] = vitem.get('Price')

    # Organize by category
    menu_by_category = {}
    for code, item in products.items():
        category = item.get('ProductType', 'Other')
        if category not in menu_by_category:
            menu_by_category[category] = []

        # Get price from variant lookup, fallback to 'N/A'
        price = product_prices.get(code, 'N/A')

        menu_by_category[category].append({
            'code': code,
            'name': item.get('Name'),
            'description': item.get('Description', ''),
            'price': price
        })

    return menu_by_category


def search_menu(store_id: str, query: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search menu items at a store.

    Args:
        store_id: Store ID
        query: Search query (optional)
        category: Category filter (optional)

    Returns:
        List of matching menu items
    """
    menu_data = api_client.get_store_menu(store_id)
    products = menu_data.get('Products', {})
    variants = menu_data.get('Variants', {})

    # Build a price lookup from variants: product_code -> first variant price
    product_prices = {}
    for vcode, vitem in variants.items():
        pc = vitem.get('ProductCode')
        if pc and pc not in product_prices:
            product_prices[pc] = vitem.get('Price')

    results = []
    for code, item in products.items():
        # Filter by category if specified
        if category and item.get('ProductType', '').lower() != category.lower():
            continue

        # Filter by search query if specified
        if query:
            name = item.get('Name', '').lower()
            desc = item.get('Description', '').lower()
            if query.lower() not in name and query.lower() not in desc:
                continue

        # Get price from variant lookup, fallback to 'N/A'
        price = product_prices.get(code, 'N/A')

        results.append({
            'code': code,
            'name': item.get('Name'),
            'category': item.get('ProductType'),
            'description': item.get('Description', ''),
            'price': price
        })

    return results


def get_coupons(store_id: str) -> List[Dict[str, Any]]:
    """
    Get available coupons/deals for a store.

    Args:
        store_id: Store ID

    Returns:
        List of available coupons sorted by price
    """
    menu_data = api_client.get_store_menu(store_id)
    coupons = menu_data.get('Coupons', {})

    coupon_list = []
    for code, coupon in coupons.items():
        price = coupon.get('Price', 999.99)
        if price is None:
            price = 999.99

        coupon_list.append({
            'code': code,
            'name': coupon.get('Name', 'Unknown Deal'),
            'description': coupon.get('Description', ''),
            'price': price,
            'tags': coupon.get('Tags', {})
        })

    # Sort by price
    coupon_list.sort(key=lambda x: x['price'])

    return coupon_list
