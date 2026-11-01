"""
Read-only price cart test.

Uses mcpizza.services.order_service.create_order to create an order,
adds pizza using real variant codes from the menu (not hard-coded product
code format), then calls api_client.price_order on current_order.data
(READ-ONLY, never place_order, no payment data) and prints the Amounts
and any StatusItems/errors.

Key findings from execution:
- The pizzapi Order.add_item() looks up codes in self.menu.variants[],
  whose code field values are like "14SCREEN", "14THIN", "PBKIREZA", etc.
- add_pizza_with_toppings() hard-codes "P{size}I{crust}" (e.g. P14IPAZA)
  which does NOT match any variant code in the API response.
- Augmenting order.data with StoreID/Email/FirstName/LastName/Phone
  is required for price_order to succeed (Status 1, non-empty Amounts).
- Coupon 5062 ("1 Large 3 Topping Pizza") works with both plain and
  pepperoni large pizzas when data is augmented.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mcpizza.services.order_service import create_order, clear_order
from mcpizza.api.client import api_client

# Delivery address from task context
ADDRESS = "102 Cainhoy Landing Rd"
CITY = "Wando"
STATE = "SC"
ZIP_CODE = "29492"
CUSTOMER_NAME = "Brandon Sheppard"
CUSTOMER_EMAIL = "brandon@example.com"
CUSTOMER_PHONE = "8435550100"


def augment(order_data):
    """Add the fields the Dominos API expects for price-order validation."""
    return dict(order_data, StoreID="7285",
                Email=CUSTOMER_EMAIL,
                FirstName=CUSTOMER_NAME.split()[0],
                LastName=CUSTOMER_NAME.split()[1] if len(CUSTOMER_NAME.split()) > 1 else "",
                Phone=CUSTOMER_PHONE)


def run_test(product_code, coupon_code=None, label=""):
    """Run a single price test and return (status, cust_amount, status_items)."""
    result = create_order(
        store_id="7285",
        customer_name=CUSTOMER_NAME,
        customer_email=CUSTOMER_EMAIL,
        customer_phone=CUSTOMER_PHONE,
        delivery_address=ADDRESS,
        delivery_city=CITY,
        delivery_state=STATE,
        delivery_zip=ZIP_CODE,
        order_type="Delivery"
    )
    current_order = __import__('mcpizza.services.order_service',
                               fromlist=['get_current_order']).get_current_order()
    current_order.add_product(product_code, None)
    if coupon_code:
        current_order.add_coupon(coupon_code)
    order_data = current_order.data
    price_result = api_client.price_order(augment(order_data))
    status = price_result.get('Status')
    amounts = price_result.get('Order', {}).get('Amounts', {}) or {}
    cust_amount = amounts.get('Customer', 'N/A')
    status_items = price_result.get('Order', {}).get('StatusItems', [])
    clear_order()
    return status, cust_amount, status_items, price_result


print("=" * 60)
print("PRICE CART TEST (READ-ONLY: price_order only)")
print("=" * 60)

# ----- Test A: Plain large hand-tossed pizza, NO coupon -----
print("\n[A] Plain large hand-tossed pizza (no coupon)")
status_a, cust_a, items_a, _ = run_test('14SCREEN')
print(f"  Status: {status_a}")
print(f"  Amounts.Customer: {cust_a}")
print(f"  StatusItems: {items_a}")

# ----- Test B: Large Ultimate Pepperoni WITH coupon 5062 -----
print("\n[B] Large Ultimate Pepperoni pizza WITH coupon 5062")
status_b, cust_b, items_b, _ = run_test('14SCPFEAST', '5062')
print(f"  Status: {status_b}")
print(f"  Amounts.Customer: {cust_b}")
print(f"  StatusItems: {items_b}")

# ----- Test C: Large hand-tossed pizza WITH coupon 5062 (S_PIZZA) -----
print("\n[C] Large hand-tossed pizza WITH coupon 5062 (S_PIZZA variant)")
status_c, cust_c, items_c, _ = run_test('14SCREEN', '5062')
print(f"  Status: {status_c}")
print(f"  Amounts.Customer: {cust_c}")
print(f"  StatusItems: {items_c}")

# ----- Summary -----
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"A: Plain large hand-tossed -> Status={status_a}, Customer={cust_a}")
print(f"B: Ultimate Pepperoni + 5062 -> Status={status_b}, Customer={cust_b}")
print(f"C: Hand-tossed + 5062 -> Status={status_c}, Customer={cust_c}")
print()
if status_a == 1 and status_b == 1 and status_c == 1:
    print("All three tests succeeded (Status 1).")
    print(f"  Plain: Amounts.Customer=${cust_a}")
    print(f"  Ultimate+coupon: Amounts.Customer=${cust_b}")
    print(f"  Hand-tossed+coupon: Amounts.Customer=${cust_c}")
else:
    print("Some tests failed (Status != 1).")
    print(f"  A: {status_a}, B: {status_b}, C: {status_c}")

print("\nNote: The pizzapi Order.add_item() uses variant codes from the")
print("menu (e.g. '14SCREEN', '14THIN', 'PBKIREZA'), NOT the hard-coded")
print("'P{size}I{crust}' format used by mcpizza.add_pizza_with_toppings().")
print("Augmenting order.data with StoreID/Email/Name/Phone is required")
print("for price_order to succeed.")