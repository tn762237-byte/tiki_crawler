import requests
import json
import time

def crawl_tiki_category(urlKey, pages=10, limit=50):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    base_url = "https://tiki.vn/api/personalish/v1/blocks/listings"

    all_products = []

    for page in range(1, pages + 1):
        params = {
            "limit": limit,
            "page": page,
            "urlKey": urlKey,      # chỉ cần urlKey
            "include": "advertisement",
            "aggregations": "2",
        }

        print(f"[INFO] Requesting page {page} ...")

        resp = requests.get(base_url, headers=headers, params=params)

        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code} page {page}: {resp.text[:200]}")
            break

        data = resp.json()

        items = data.get("data", [])
        if not items:
            print("[END] No more data.")
            break

        all_products.extend(items)
        print(f"  -> fetched {len(items)} items")

        time.sleep(0.5)

    print(f"\n[TOTAL] Crawled {len(all_products)} products")
    return all_products


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    urlKey = "nha-sach-tiki/c8322"
    products = crawl_tiki_category(urlKey=urlKey, pages=10, limit=50)

    with open("tiki_8322.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print("Saved to tiki_8322.json")
