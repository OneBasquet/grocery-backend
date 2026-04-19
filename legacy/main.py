import os
import random
import pandas as pd
from dotenv import load_dotenv
from apify_client import ApifyClient

# --- SETUP ---
load_dotenv()
client = ApifyClient(os.getenv("APIFY_TOKEN"))

def generate_mock_data(tesco_item, retailer):
    """Generates a plausible price match for validation purposes."""
    # Simulate a price that is +/- 10% of Tesco
    variation = random.uniform(0.9, 1.1)
    return {
        "name": f"[{retailer}] {tesco_item['name']}",
        "gtin": tesco_item['gtin'],
        "price": round(tesco_item['price'] * variation, 2),
        "retailer": retailer,
        "is_mock": True
    }

def run_hybrid_validation(query):
    all_data = []
    
    # 1. REAL FETCH (Tesco)
    try:
        print(f"📡 Harvesting REAL data from Tesco...")
        run = client.actor("radeance/tesco-scraper").call(run_input={"keyword": query, "max_items": 5})
        tesco_raw = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        
        for item in tesco_raw:
            normalized = {
                "name": item.get("name"),
                "gtin": item.get("gtin"),
                "price": float(item.get("price", 0)),
                "retailer": "Tesco",
                "is_mock": False
            }
            all_data.append(normalized)
        print(f"✅ Tesco Success: {len(tesco_raw)} items.")
    except Exception as e:
        print(f"❌ Tesco Failed: {e}")

    # 2. MOCK FALLBACK (Sainsbury & Asda)
    # We do this so you can test your 'Best Price' logic today
    if all_data:
        print("🎭 Generating Mock data for Sainsbury and Asda to test logic...")
        tesco_only = [i for i in all_data if i['retailer'] == 'Tesco' and i['gtin']]
        for item in tesco_only:
            all_data.append(generate_mock_data(item, "Sainsbury"))
            all_data.append(generate_mock_data(item, "Asda"))

    return all_data

if __name__ == "__main__":
    snapshot = run_hybrid_validation("Lurpak")
    
    if snapshot:
        df = pd.DataFrame(snapshot)
        # Pivot the table to see the comparison clearly
        report = df.pivot_table(index=['gtin'], columns='retailer', values='price')
        
        print("\n" + "="*60)
        print("PROTOTYPE COMPARISON REPORT (Mix of Real & Mock)")
        print("="*60)
        print(report)
        
        # Determine the winner for each GTIN
        report['Winner'] = report.idxmin(axis=1)
        print("\n--- Market Insights ---")
        print(report[['Winner']])
    else:
        print("No data available.")