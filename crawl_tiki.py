#!/usr/bin/env python3
# crawl_tiki.py
"""
Crawl products from Tiki category API and save to CSV.
Uses requests + Tiki API endpoints (no Selenium).
Delay 1s between page requests, fake User-Agent, retry on failures.
Collect up to N products per category.
"""

import requests
import time
import csv
import re
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# ====== CONFIG ======
# Fake User-Agent header (common modern browser UA)
HEADERS = {
    # Dùng User-Agent hiện tại của bạn
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", 
    "Accept": "*/*", # Cập nhật: Dùng */*
    # CÁC HEADERS BẮT BUỘC để tránh lỗi 400, lấy từ Dev Tools:
    "sec-fetch-mode": "cors", 
    "sec-fetch-site": "cross-site",
    "sec-fetch-dest": "empty",
    "sec-ch-ua-platform": "\"Windows\"", 
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    # Referer sẽ được xử lý động trong hàm fetch_category_products
}
PER_CATEGORY_LIMIT = 100  # number of products to collect per category
PAGE_LIMIT = 40  # items per page (Tiki typical); we request limit=40
DELAY_BETWEEN_REQUESTS = 1.0  # seconds (anti-block)
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"tiki_products_{datetime.now().strftime('%Y%m%d')}.csv")

# requested fields (order preserved)
FIELDS = [
    "id","sku","name","url_key","url_path","type","author_name","book_cover","brand_name",
    "short_description","price","list_price","badges","badges_new","discount","discount_rate",
    "rating_average","review_count","order_count","favourite_count","thumbnail_url",
    "thumbnail_width","thumbnail_height","freegift_items","has_ebook","inventory_status",
    "is_visible","productset_id","productset_group_name","seller","is_flower","is_gift_card",
    "inventory","url_attendant_input_form","option_color","stock_item","salable_type",
    "seller_product_id","installment_info","url_review","bundle_deal","quantity_sold",
    "tiki_live","original_price","shippable","impression_info","advertisement","availability",
    "primary_category_path","product_reco_score","seller_id","visible_impression_info",
    "badges_v3","has_video"
]

# ĐÃ XÓA KHỐI HEADERS TRÙNG LẶP Ở ĐÂY (dòng 86-93 trong code gốc)

# ====== utility functions ======

def extract_category_id(url: str) -> Optional[str]:
    """Extract category id from url like '/c1234'."""
    m = re.search(r"/c(\d+)(?:$|[/?])", url)
    return m.group(1) if m else None

def safe_get_recursive(obj: Any, key: str) -> Any:
    """
    Search for key in nested dict/list structures recursively.
    Return first match or None.
    """
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = safe_get_recursive(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = safe_get_recursive(item, key)
            if found is not None:
                return found
    return None

def get_field(item: Dict[str, Any], field: str) -> Any:
    """
    Try to get 'field' from item:
    - direct key
    - nested recursive search
    - some field-specific fallbacks for common tiki structure
    """
    if field in item:
        return item.get(field)
    # common nested names
    # try direct nested places
    # e.g. seller info often in item.get('seller') or item.get('current_seller')
    fallback = safe_get_recursive(item, field)
    if fallback is not None:
        return fallback

    # additional heuristic fallbacks:
    if field == "thumbnail_url":
        # common keys
        for k in ("thumbnail_url", "thumbnail", "image", "product_thumbnail"):
            v = safe_get_recursive(item, k)
            if v:
                return v
    if field == "price":
        for k in ("price", "final_price", "discounted_price", "price_sale"):
            v = safe_get_recursive(item, k)
            if v is not None:
                return v
    if field == "list_price" or field == "original_price":
        for k in ("list_price", "original_price", "price_before_discount", "price_old"):
            v = safe_get_recursive(item, k)
            if v is not None:
                return v
    if field == "rating_average":
        return safe_get_recursive(item, "rating_average") or safe_get_recursive(item, "average_rating") or safe_get_recursive(item, "rating")
    if field == "review_count":
        return safe_get_recursive(item, "review_count") or safe_get_recursive(item, "review_total") or safe_get_recursive(item, "reviews")
    # default None
    return None

def build_product_row(product_json: Dict[str, Any]) -> Dict[str, Any]:
    """Map product json to CSV row using FIELDS list."""
    row = {}
    for f in FIELDS:
        val = get_field(product_json, f)
        # For lists/dicts, dump as JSON string
        if isinstance(val, (dict, list)):
            try:
                row[f] = json.dumps(val, ensure_ascii=False)
            except Exception:
                row[f] = str(val)
        else:
            row[f] = val
    return row

# ====== main crawling logic ======

def fetch_category_products(category_url: str, per_category_limit: int = PER_CATEGORY_LIMIT) -> List[Dict[str, Any]]:
    """
    Use Tiki listing API to fetch products for a category.
    Pattern used: https://tiki.vn/api/personalish/v1/blocks/listings?limit=40&category_id={cat_id}&page={page}
    """
    cat_id = extract_category_id(category_url)
    if not cat_id:
        print(f"[WARN] Cannot extract category id from {category_url}")
        return []

    products = []
    page = 1
    limit = PAGE_LIMIT
    
    # 1. BỔ SUNG: Chuẩn bị Headers đã bao gồm Referer động
    request_headers = HEADERS.copy()
    request_headers['Referer'] = category_url # Gán Referer là URL danh mục hiện tại

    while len(products) < per_category_limit:
        params = {
            "limit": limit,
            "category_id": cat_id,
            "page": page,
            # 2. BỔ SUNG: Thêm Query Parameters bị thiếu (thường gây lỗi 400)
            "platform": "desktop", 
            "sort": "default"      
        }
        url = "https://tiki.vn/api/personalish/v1/blocks/listings"
        try:
            # SỬ DỤNG request_headers (có Referer)
            resp = requests.get(url, headers=request_headers, params=params, timeout=30)
            
            # 3. SỬA LỖI: Xử lý lỗi 400 và lỗi khác
            if resp.status_code == 400:
                print(f"[FATAL] HTTP 400 Bad Request for category {cat_id} page {page}. Parameters/Headers are likely incorrect. Stopping category.")
                break # Dừng hẳn danh mục này
            
            if resp.status_code != 200:
                print(f"[ERROR] HTTP {resp.status_code} for category {cat_id} page {page} - Retrying after delay...")
                time.sleep(DELAY_BETWEEN_REQUESTS * 2) 
                continue

            data = resp.json()
            # The API returns a structure; products often under data['data'] or data['items'] or data['records']
            block_items = None
            for candidate in ("data", "items", "records", "collection", "products"):
                if candidate in data and isinstance(data[candidate], (list, dict)):
                    block_items = data[candidate]
                    break
            # if 'data' is a dict with 'items' inside
            if block_items is None and isinstance(data.get("data"), dict):
                for c in ("items","data","records"):
                    if c in data["data"]:
                        block_items = data["data"][c]
                        break
            # if block_items is dict (maybe paged), try extract list from common keys
            if isinstance(block_items, dict):
                # look for 'items' or 'data'
                for c in ("items", "data", "records", "products"):
                    if c in block_items and isinstance(block_items[c], list):
                        block_items = block_items[c]
                        break

            if not block_items:
                # fallback: try to look recursively for product objects
                # naive: if 'data' has 'listing' etc
                # We'll try searching for a list anywhere in the response that has dicts with 'id' key
                found = None
                def find_list_with_id(obj):
                    if isinstance(obj, list):
                        if len(obj) > 0 and isinstance(obj[0], dict) and "id" in obj[0]:
                            return obj
                        for it in obj:
                            res = find_list_with_id(it)
                            if res:
                                return res
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            res = find_list_with_id(v)
                            if res:
                                return res
                    return None
                found = find_list_with_id(data)
                block_items = found

            if not block_items:
                print(f"[WARN] no items found on category {cat_id} page {page}. Response keys: {list(data.keys())}")
                break

            # ensure list
            if isinstance(block_items, dict):
                block_items = [block_items]

            # iterate and append
            for it in block_items:
                # sometimes the item is a 'product' wrapper
                prod = it
                # find inner product if nested
                if isinstance(it, dict):
                    if "product" in it and isinstance(it["product"], dict):
                        prod = it["product"]
                    elif "item" in it and isinstance(it["item"], dict):
                        prod = it["item"]
                if isinstance(prod, dict):
                    products.append(prod)
                if len(products) >= per_category_limit:
                    break

            print(f"[INFO] category {cat_id} page {page} -> got {len(block_items)} items; total collected: {len(products)}")
            page += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)

        except Exception as e:
            print(f"[ERROR] Exception while fetching category {cat_id} page {page}: {e}")
            time.sleep(3)
            page += 1
            continue

    return products[:per_category_limit]

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_rows = []
    # LƯU Ý: Đảm bảo biến CATEGORIES đã được định nghĩa ở đâu đó trong code của bạn
    # Ví dụ: CATEGORIES = ["https://tiki.vn/dien-thoai-smartphone/c1795"]
    for cat_url in CATEGORIES: 
        print(f"[START] crawling category: {cat_url}")
        prods = fetch_category_products(cat_url, per_category_limit=PER_CATEGORY_LIMIT)
        print(f"[DONE] category {cat_url} -> collected {len(prods)} products")
        for p in prods:
            row = build_product_row(p)
            # also add a source_category field for traceability
            row["_source_category_url"] = cat_url
            all_rows.append(row)

    # Ensure header includes FIELDS + source column
    headers = FIELDS + ["_source_category_url"]
    # write CSV
    print(f"[WRITE] saving {len(all_rows)} rows to {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for r in all_rows:
            # ensure all headers exist in row
            out = {h: (r.get(h) if r.get(h) is not None else "") for h in headers}
            writer.writerow(out)

    print("[FIN] crawling finished")

if __name__ == "__main__":
    main()
