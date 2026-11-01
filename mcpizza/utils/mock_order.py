"""
Mock order object creation for bypassing pizzapi menu parsing bugs
"""
import types
from typing import Any, Optional, Dict


def create_mock_order(store: Any, customer: Any, address: Any, order_type: str) -> Any:
    """
    Create a mock order object that has the essential attributes
    but skips menu loading (which has bugs in pizzapi).

    Args:
        store: Store object from pizzapi
        customer: Customer object from pizzapi
        address: Address object from pizzapi
        order_type: "Delivery" or "Carryout"

    Returns:
        Mock order object with data dict and helper methods
    """
    order = types.SimpleNamespace()
    order.store = store
    order.customer = customer
    order.address = address
    order.data = {
        'Address': {
            'Street': address.street,
            'City': address.city,
            'Region': address.region,
            'PostalCode': address.zip,
            'Type': 'House'
        },
        'Coupons': [],
        'CustomerID': '',
        'Extension': '',
        'OrderChannel': 'OLO',
        'OrderID': '',
        'NoCombine': True,
        'OrderMethod': 'Web',
        'OrderTaker': None,
        'Payments': [],
        'Products': [],
        'Market': '',
        'Currency': '',
        'ServiceMethod': order_type,
        'Tags': {},
        'Version': '1.0',
        'SourceOrganizationURI': 'order.dominos.com',
        'LanguageCode': 'en',
        'Partners': {},
        'NewUser': True,
        'metaData': {},
        'Amounts': {},
        'BusinessDate': '',
        'EstimatedWaitMinutes': '',
        'PriceOrderTime': '',
        'AmoundsBreakdown': {}
    }

    # Add menu attribute (unused but expected)
    order.menu = None

    # Add helper methods
    def add_coupon(coupon_code: str):
        """Add coupon to order"""
        order.data['Coupons'].append({
            'Code': coupon_code,
            'Qty': 1,
            'ID': len(order.data['Coupons']) + 1
        })

    def add_product(product_code: str, options: Optional[Dict] = None, quantity: int = 1):
        """Add product with toppings to order"""
        order.data['Products'].append({
            'Code': product_code,
            'Qty': quantity,
            'ID': len(order.data['Products']) + 1,
            'isNew': True,
            'Options': options or {}
        })

    order.add_coupon = add_coupon
    order.add_product = add_product

    return order
