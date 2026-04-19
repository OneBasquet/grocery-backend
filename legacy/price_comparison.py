import pandas as pd

def compare_prices(normalized_items):
    """
    Groups items by GTIN and identifies the cheapest options.
    """
    if not normalized_items:
        return "No data to compare."

    # 1. Convert to DataFrame for easy manipulation
    df = pd.DataFrame(normalized_items)

    # 2. Filter out items without a GTIN (they can't be matched reliably)
    df = df.dropna(subset=['universal_id'])

    # 3. Sort by 'unit_price' to find the best value, not just lowest tag price
    # Some stores might have a smaller pack for cheaper, but it's worse value.
    df_sorted = df.sort_values(by=['universal_id', 'unit_price'])

    # 4. Find the "Winner" for each unique product
    winners = df_sorted.drop_duplicates(subset=['universal_id'], keep='first')

    return winners

# --- Let's Simulate Data from Two Different Retailers ---
mock_normalized_data = [
    {
        "universal_id": "05011037611195", # Dairygold Butter
        "retailer": "TESCO",
        "current_price": 3.50,
        "unit_price": 7.71,
        "product_name": "Dairygold 454G"
    },
    {
        "universal_id": "05011037611195", # SAME GTIN
        "retailer": "SAINSBURYS",
        "current_price": 3.20,
        "unit_price": 7.05,
        "product_name": "Dairygold Butter 454G"
    },
    {
        "universal_id": "99999999999999", # Different Product (Milk)
        "retailer": "TESCO",
        "current_price": 1.50,
        "unit_price": 0.75,
        "product_name": "Whole Milk 2L"
    }
]

# Run Comparison
best_deals = compare_prices(mock_normalized_data)
print("--- Best Deals Found ---")
print(best_deals[['product_name', 'retailer', 'current_price', 'unit_price']])
