"""
Smoke test: import mcpizza.services.store_service and call
find_stores/get_menu/get_coupons for ZIP 29464 (Mount Pleasant SC).
"""
from mcpizza.services.store_service import find_stores, get_menu, get_coupons

if __name__ == "__main__":
    zip_code = "29464"
    print(f"Looking up stores for ZIP {zip_code}...\n")

    # 1. find_stores
    stores = find_stores(zip_code)
    print(f"find_stores returned {len(stores)} store(s):")
    for i, s in enumerate(stores):
        print(f"  Store {i+1}: id={s['id']}, address={s['address']}, phone={s['phone']}, is_open={s['is_open']}")

    if not stores:
        print("No stores found. Exiting.")
        exit(0)

    first_store_id = stores[0]['id']
    print(f"\nFirst store ID: {first_store_id}\n")

    # 2. get_menu
    print("get_menu for first store:")
    menu = get_menu(first_store_id)
    for category, items in menu.items():
        print(f"  Category: {category}")
        for item in items[:3]:  # show first 3 per category
            print(f"    - {item['code']}: {item['name']} (price: {item['price']})")

    # 3. get_coupons
    print("\nget_coupons for first store:")
    coupons = get_coupons(first_store_id)
    print(f"  Total coupons: {len(coupons)}")
    for i, c in enumerate(coupons[:10]):
        print(f"    Coupon {i+1}: code={c['code']}, name={c['name']}, price={c['price']}")

    print("\nDone.")