# MCP Pizza Ordering Workflow

## Overview
MCP Pizza is a Model Context Protocol server that enables AI assistants to price and, when explicitly enabled, place pizza orders through Domino's API.

## Important Notes
- **Placement is a dry run by default.** Real orders need `MCPIZZA_ALLOW_PLACE=1` and a card file (`MCPIZZA_CARD_FILE`). See docs/SECURITY.md.
- All interactions are logged to `logs/interactions_YYYYMMDD.log`
- Coupons are added to the `Coupons` array, not `Products`
- The system uses a mock Order object that makes real API calls

## Complete Ordering Workflow

### Step 1: Find Nearby Stores
```
Tool: find_stores
Parameters: { "query": "76104" }
```
Returns list of stores with IDs, addresses, and open/closed status.

### Step 2: Get Store Information (Optional)
```
Tool: get_store_info
Parameters: { "store_id": "8022" }
```
Returns detailed store info including hours and services.

### Step 3: Get Available Coupons
```
Tool: get_coupons
Parameters: { "store_id": "8022" }
```
Returns all available deals sorted by price. **Essential for getting the right coupon codes.**

### Step 4: Get Ordering Guidance (Optional but Recommended)
```
Tool: get_ordering_guidance
Parameters: {
  "store_id": "8022",
  "user_request": "deep dish sausage and pepperoni"
}
```
Analyzes deals and recommends the best approach for the user's request.

### Step 5: Create Order
```
Tool: create_order
Parameters: {
  "store_id": "8022",
  "customer_name": "John Doe",
  "customer_email": "john.doe@example.com",
  "customer_phone": "5555551234",
  "delivery_address": "123 Main St",
  "delivery_city": "Fort Worth",
  "delivery_state": "TX",
  "delivery_zip": "76102",
  "order_type": "Carryout"
}
```

**IMPORTANT:**
- `order_type` must be either "Carryout" or "Delivery"
- Creates a mock order object that makes real API calls

### Step 6: Add Pizza with Toppings (RECOMMENDED)
```
Tool: add_pizza_with_toppings
Parameters: {
  "coupon_code": "9204",
  "size": "12",
  "crust": "NPAN",
  "toppings": ["P", "S"]
}
```

**This is the proper way to add a customized pizza:**
- Adds the coupon to `Coupons` array
- Adds the pizza product with toppings to `Products` array
- Handles all the complexity of Domino's product codes and topping format

**Common topping codes:**
- `P` = Pepperoni
- `S` = Sausage
- `M` = Mushrooms
- `O` = Onions
- `B` = Beef
- `K` = Bacon
- `H` = Ham

**Common crust codes:**
- `NPAN` = Handmade Pan (deep dish)
- `HAND` = Hand Tossed
- `THIN` = Thin Crust
- `BROOKLYN` = Brooklyn Style

### Step 6 Alternative: Add Simple Items
```
Tool: add_item_to_order
Parameters: {
  "item_code": "9204",
  "quantity": 1
}
```

**WARNING:** This only adds the coupon code without pizza configuration. Use `add_pizza_with_toppings` instead for customized pizzas.

### Step 7: View Order (Verify Before Placing)
```
Tool: view_order
Parameters: {}
```
Shows:
- Store ID and customer info
- All coupons added to the order
- All products added to the order
- Pricing (if available)

### Step 8: Prepare the Order
```
Tool: prepare_order
Parameters: {}
```
Validates and prices the order, then returns a read-back (store, items, total) and a `confirm_token`. Show the read-back to the human. The token is single use, expires in 10 minutes, and is bound to the order contents; changing the order invalidates it.

### Step 9: Place the Order
```
Tool: place_order
Parameters: { "confirm_token": "<token from prepare_order>" }
```
Only the token is accepted. The card is loaded server-side from `MCPIZZA_CARD_FILE`.

- Without `MCPIZZA_ALLOW_PLACE=1` this is a **dry run**: it checks everything and reports what it would send.
- With it, the order is submitted to Domino's. Live submission is not yet verified end to end and may hit a CAPTCHA.

## Coupon vs Product Distinction

### Coupons (Deals)
- Examples: "9204", "4342", "5385"
- Added to `order.data['Coupons']` array
- Found via `get_coupons` tool
- Usually come with fixed prices (like $10.99)
- Domino's API validates and applies them during pricing

### Products (Individual Items)
- Examples: Pizza toppings, sides, drinks
- Would be added to `order.data['Products']` array
- Found via `search_menu` or `get_menu` tools
- Have individual item codes

**Current Implementation:** The `add_item_to_order` function adds everything to the `Coupons` array. This works for coupon-based ordering.

## Stored Customer Information

Customer data can be saved in `.customer_info.json` (gitignored):
```json
{
  "customer": {
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "5555551234"
  },
  "address": {
    "street": "123 Main St",
    "city": "Fort Worth",
    "state": "TX",
    "zip": "76102"
  },
  "preferred_store": "8022",
  "order_preferences": {
    "default_pizza": "deep dish sausage and pepperoni",
    "default_deal": "9204",
    "order_type": "Carryout"
  },
  "payment": {
    "_note": "card data is never stored here; see MCPIZZA_CARD_FILE"
  }
}
```

## Logging System

All MCP interactions are logged to `logs/interactions_YYYYMMDD.log` in JSON format:

### Log Entry Types:
1. **LIST_TOOLS** - Tool list requests
2. **TOOL_CALL** - Incoming tool invocations with full arguments
3. **TOOL_RESPONSE** - Outgoing responses (500-char preview)
4. **STATE_CHANGE** - Order creation, item additions, order clearing
5. **ERROR** - Any errors during execution

### Example Log Entry:
```json
{
  "type": "tool_call",
  "direction": "incoming",
  "tool_name": "create_order",
  "arguments": {...},
  "timestamp": "2025-12-05T21:09:27.509040"
}
```

## Error Handling

### Common Errors:

1. **Invalid ProductCode**
   - Cause: Trying to add a coupon code as a product
   - Solution: Coupons go in `Coupons` array, not `Products`

2. **Pricing Failed (Status: -1)**
   - Cause: Invalid coupon, store closed, or items not available
   - Solution: Check coupon validity and store hours

3. **Order placement failed**
   - Cause: Payment declined, store not accepting orders, or API limitations
   - Solution: Verify payment info and store status

## Technical Implementation Details

### Mock Order Object
The system uses a mock order object (via `types.SimpleNamespace`) because pizzapi's `Order()` initialization fails due to menu parsing bugs.

The mock object has:
- `order.data` - Complete order structure
- `order.add_item()` - Adds items to Coupons array
- `order.place()` - Makes real API calls to Domino's

### API Endpoints Used:
- `https://order.dominos.com/power/store/{id}` - Store info
- `https://order.dominos.com/power/store/{id}/menu?lang=en&structured=true` - Menu/coupons
- `https://order.dominos.com/power/price-order` - Validate and price order
- `https://order.dominos.com/power/place-order` - Submit order

## Testing
Run the autonomous test suite:
```bash
python3 test_mcp_with_ollama.py
```

This tests all functionality except actual order placement.

## Recent Updates

### ✅ Added `add_pizza_with_toppings` Tool
- Properly handles coupon + product + toppings
- Automatically builds correct product codes
- Supports all major crust types and toppings
- This is now the recommended way to order customized pizzas

## Future Improvements

1. **Better coupon validation** - Check coupon validity before adding to order
2. **Topping portions** - Support for light/extra toppings
3. **Half-and-half pizzas** - Different toppings on each half
4. **Order history** - Track previous orders
5. **Multiple payment methods** - Support cash, gift cards, etc.
