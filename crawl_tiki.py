import requests
import time

CATEGORY_ID = 8322
TARGET_TOTAL = 50
LIMIT = 20
API_URL = "https://tiki.vn/api/v2/products"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

def crawl_category(category_id, target_total=50):
    results = []
    page = 1

    while len(results) < target_total:
        params = {
            "limit": LIMIT,
            "category": category_id,
            "page": page
        }

        print(f"[DEBUG] Requesting page {page} ...")
        resp = requests.get(API_URL, headers=HEADERS, params=params)

        if resp.status_code != 200:
            print("[ERROR] HTTP:", resp.status_code)
            break

        data = resp.json()

        items = data.get("data", [])
        if not items:
            print("[INFO] Hết sản phẩm. Dừng.")
            break

        for item in items:
            results.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price"),
                "url": "https://tiki.vn/" + item.get("url_path", "")
            })

            if len(results) >= target_total:
                break

        print(f"[INFO] Đã lấy {len(results)} sản phẩm.")
        page += 1
        time.sleep(0.3)

    return results


# ---- RUN ----
products = crawl_category(CATEGORY_ID, TARGET_TOTAL)

print("\n==== RESULT ====")
for p in products:
    print(p)

print("\nTotal:", len(products))
