import requests
import time

CATEGORY_ID = 8322
CATEGORY_SLUG = "nha-sach-tiki"
LIMIT_EACH_PAGE = 20         # mỗi request trả 20 sp
TARGET_TOTAL = 50            # mục tiêu cần crawl
API_URL = "https://tiki.vn/api/personalish/v1/blocks/listings"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": f"https://tiki.vn/{CATEGORY_SLUG}/c{CATEGORY_ID}"
}

def crawl_category(category_id, slug, target_total=50):
    results = []
    page = 1

    while len(results) < target_total:
        params = {
            "limit": LIMIT_EACH_PAGE,
            "page": page,
            "urlKey": slug,
            "category": category_id,
            "sort": "default",
            "include": "advertisement",
            "aggregations": "2"
        }

        print(f"[DEBUG] Request page {page} ...")

        resp = requests.get(API_URL, headers=HEADERS, params=params)
        print("[DEBUG] Status:", resp.status_code)

        if resp.status_code != 200:
            print("Stop: Unexpected HTTP", resp.status_code)
            break

        data = resp.json()
        
        # Tiki luôn dùng "data" -> "items"
        items = data.get("data", {}).get("items", [])

        if not items:
            print("[INFO] Không có sản phẩm nào nữa. Dừng.")
            break

        for item in items:
            results.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price"),
                "url": f"https://tiki.vn/{item.get('url_path')}"
            })

            if len(results) >= target_total:
                break

        print(f"[INFO] Đã lấy {len(results)} sản phẩm.")
        page += 1
        time.sleep(0.5)

    return results


# ---- RUN ----
products = crawl_category(CATEGORY_ID, CATEGORY_SLUG, TARGET_TOTAL)

print("\n==== RESULT ====")
for p in products:
    print(p)

print("\nTotal:", len(products))
