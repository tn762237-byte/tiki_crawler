# crawl_tiki_fallback.py
import requests
import time
import sys
from urllib.parse import urlencode
from bs4 import BeautifulSoup

# Cấu hình
CATEGORY_ID = 8322
CATEGORY_SLUG = "nha-sach-tiki"
TARGET_TOTAL = 50
PAGE_LIMIT = 20      # limit mỗi trang khi gọi API
DELAY = 0.3

# Option: nếu bạn có cookie / header đặc biệt (ví dụ từ trình duyệt) -> gán vào COOKIE_STRING
COOKIE_STRING = None  # Ví dụ: "sid=...; other=..."  hoặc None để không dùng

# Session chung
session = requests.Session()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"https://tiki.vn/{CATEGORY_SLUG}/c{CATEGORY_ID}",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}
if COOKIE_STRING:
    session.headers.update({"Cookie": COOKIE_STRING})
session.headers.update(HEADERS)

# Endpoints to try (in order)
ENDPOINTS = [
    {"name": "v2_products", "url": "https://tiki.vn/api/v2/products", "use_category_param": True},
    {"name": "personalish_with_id", "url": "https://tiki.vn/api/personalish/v1/blocks/listings", "use_category_param": True},
    {"name": "personalish_with_str", "url": "https://tiki.vn/api/personalish/v1/blocks/listings", "use_category_param": False},
    {"name": "v2_search", "url": "https://tiki.vn/api/v2/search", "use_category_param": True},
]

def debug_print_resp(resp):
    print("[DEBUG] status:", resp.status_code)
    print("[DEBUG] final url:", resp.url)
    text_snippet = (resp.text[:1000] + '...') if len(resp.text) > 1000 else resp.text
    print("[DEBUG] resp text snippet (first 1000 chars):")
    print(text_snippet)

def try_api_products(endpoint, category_id, slug, target):
    products = []
    page = 1
    url_base = endpoint["url"]
    use_cat_param = endpoint.get("use_category_param", True)

    while len(products) < target:
        params = {"limit": PAGE_LIMIT, "page": page}
        # some endpoints expect numeric category param, some expect string slug
        if use_cat_param:
            params["category"] = category_id
        else:
            # send as string/category slug
            params["category"] = str(category_id)  # try string version
            params["urlKey"] = slug

        try:
            resp = session.get(url_base, params=params, timeout=15)
        except Exception as e:
            print(f"[WARN] Request exception: {e}")
            return products, resp if 'resp' in locals() else None, False

        # Always log when not 200
        if resp.status_code != 200:
            print(f"[WARN] Endpoint {endpoint['name']} returned {resp.status_code} on page {page}")
            debug_print_resp(resp)
        # If 400 specifically, return to allow fallback
        if resp.status_code == 400:
            return products, resp, False

        # If other non-200, try small retry
        if resp.status_code != 200:
            time.sleep(DELAY * 3)
            page += 1
            if page > 5:
                # give up on this endpoint
                return products, resp, False
            continue

        # Parse json
        try:
            j = resp.json()
        except Exception as e:
            print("[ERROR] Response not JSON. Debug info:")
            debug_print_resp(resp)
            return products, resp, False

        # Try to extract items from common paths
        items = None
        if isinstance(j, dict):
            for k in ("data", "items", "products", "records"):
                if k in j and isinstance(j[k], list):
                    items = j[k]
                    break
            # some v2/products: {"data": [...]} or {"data": {"products": [...]}}
            if items is None and "data" in j and isinstance(j["data"], (list, dict)):
                if isinstance(j["data"], list):
                    items = j["data"]
                elif isinstance(j["data"], dict):
                    for k in ("items", "products", "records"):
                        if k in j["data"] and isinstance(j["data"][k], list):
                            items = j["data"][k]
                            break

        # If still None, log and stop this endpoint
        if items is None:
            print(f"[WARN] Could not find items array for endpoint {endpoint['name']} on page {page}. Keys: {list(j.keys()) if isinstance(j, dict) else 'not-dict'}")
            debug_print_resp(resp)
            return products, resp, False

        # If empty list -> end of pagination
        if not items:
            print(f"[INFO] No items on page {page} for endpoint {endpoint['name']}. Ending.")
            return products, resp, True

        # Normalize and append
        for it in items:
            # many responses include fields id, name, price, url_path
            pid = it.get("id") or it.get("product_id")
            name = it.get("name") or it.get("title")
            price = it.get("price") or it.get("final_price") or None
            url_path = it.get("url_path") or it.get("url") or it.get("short_url") or it.get("product_url")
            url_full = None
            if url_path:
                if url_path.startswith("http"):
                    url_full = url_path
                else:
                    url_full = "https://tiki.vn/" + url_path.lstrip("/")
            products.append({"id": pid, "name": name, "price": price, "url": url_full})
            if len(products) >= target:
                break

        print(f"[INFO] endpoint {endpoint['name']} page {page} -> got {len(items)} items, collected total {len(products)}")
        page += 1
        time.sleep(DELAY)

    return products, resp, True

def fallback_html_scrape(category_url, target):
    print("[INFO] Using HTML fallback to scrape product links from category page.")
    products = []
    page = 1
    seen_urls = set()
    while len(products) < target:
        # Tiki category has pagination via ?page=2 etc (also infinite load) — try page query
        url = category_url
        if page > 1:
            url = f"{category_url}?page={page}"
        print(f"[DEBUG] Scraping HTML: {url}")
        try:
            resp = session.get(url, timeout=15)
        except Exception as e:
            print("[ERROR] HTML request failed:", e)
            break
        if resp.status_code != 200:
            print("[WARN] HTML page returned", resp.status_code)
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        # Tiki renders product cards with <a data-view-id or class "product-item" or attribute href contains "/p/"
        anchors = soup.find_all("a", href=True)
        found = 0
        for a in anchors:
            href = a["href"]
            # heuristics for product path: often contains "-p" or "/product-name-p" or "tiki.vn/<slug>/p<id>"
            if "/p/" in href or href.count("-p") >= 1 or href.startswith("/"):
                # normalize tiki product url
                if href.startswith("http"):
                    u = href
                else:
                    u = "https://tiki.vn" + href
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                name = (a.get("title") or a.text or "").strip()
                products.append({"id": None, "name": name, "price": None, "url": u})
                found += 1
                if len(products) >= target:
                    break
        print(f"[INFO] HTML page {page} found {found} product links, total collected: {len(products)}")
        if found == 0:
            # probably no more pages
            break
        page += 1
        time.sleep(DELAY)
    return products

def main():
    category_url = f"https://tiki.vn/{CATEGORY_SLUG}/c{CATEGORY_ID}"
    collected = []
    last_resp = None

    # Try endpoints in order
    for ep in ENDPOINTS:
        print(f"[TRY] Endpoint: {ep['name']} -> {ep['url']}")
        prods, resp, ok = try_api_products(ep, CATEGORY_ID, CATEGORY_SLUG, TARGET_TOTAL)
        last_resp = resp
        if prods:
            collected = prods
            print(f"[OK] Collected {len(collected)} products using endpoint {ep['name']}.")
            break
        else:
            print(f"[INFO] Endpoint {ep['name']} returned no products or failed. ok={ok}")
            # if we got 400, print resp and stop trying this endpoint, continue to next
            if resp is not None and resp.status_code == 400:
                print("[WARN] Got 400. Response snippet below for debugging:")
                debug_print_resp(resp)
            # continue to try next endpoint

    # If none of the API endpoints produced results, fallback to HTML scrape
    if not collected:
        print("[FALLBACK] No API endpoint worked — switching to HTML scraping.")
        collected = fallback_html_scrape(category_url, TARGET_TOTAL)

    # Trim to TARGET_TOTAL
    collected = collected[:TARGET_TOTAL]
    print("\n===== RESULT =====")
    for i, p in enumerate(collected, start=1):
        print(i, p)
    print("Total:", len(collected))

    # If last_resp exists and had non-200, suggest copying debug output to share
    if last_resp is not None and last_resp.status_code != 200:
        print("\n--- DEBUG HELP ---")
        print("If you still see errors, please copy these details and paste to me:")
        print("1) Last response status:", last_resp.status_code)
        print("2) Last response URL:", last_resp.url)
        snippet = (last_resp.text[:1500] + '...') if len(last_resp.text) > 1500 else last_resp.text
        print("3) Last response text (first 1500 chars):\n", snippet)

if __name__ == "__main__":
    main()
