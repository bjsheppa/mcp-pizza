# Pricing Findings for MCPizza

## Root Cause of "price: N/A"

The `get_menu()` function in `mcpizza/services/store_service.py` extracts prices from the top-level product objects using `item.get('Price', 'N/A')`. However, the Domino's API response structure has the actual prices in a separate `Variants` dictionary.

### API Response Structure

From `https://order.dominos.com/power/store/7285/menu?lang=en&structured=true`:

- **`Products`** dict (67 entries): Contains product metadata (name, description, ProductType) but **all have `Price: None`**
  - Example: `S_PIZZA` - Price: `None`
  - Example: `S_PIZPX` (Ultimate Pepperoni) - Price: `None`
  - Example: `F_PBITES` (Parmesan Bread Bites) - Price: `None`

- **`Variants`** dict (212 entries): Contains the actual pricing information
  - Each variant has: `ProductCode`, `SizeCode`, `Price`, `Name`
  - Example: Variant `B16PBIT` for `F_PBITES`: Size `BRD16`, Price `$5.49`
  - Example: Variant for `S_PIZZA` size 12: Price `$11.99`
  - Example: Variant for `S_PIZPX` size 14: Price `$18.99`

### Location of the Bug

**File:** `mcpizza/services/store_service.py`
- Line 94: `'price': item.get('Price', 'N/A')` in `get_menu()`
- Line 133: `'price': item.get('Price', 'N/A')` in `search_menu()`

Both functions extract price from the top-level `Products` dict where `Price` is always `None`, instead of looking up the price from the `Variants` dict.

### Fix Approach

For each product, look up its price from the `Variants` dictionary by matching `ProductCode`. Use the first available variant's price for each product.

**Proposed patch for `store_service.py`:**

1. After getting `menu_data`, build a `product_prices` dict by iterating over `variants` and recording the first variant price per `ProductCode`
2. Use `product_prices.get(code, 'N/A')` instead of `item.get('Price', 'N/A')` when building menu items

This is a minimal, focused change that only modifies the price extraction logic in `get_menu()` and `search_menu()`.
