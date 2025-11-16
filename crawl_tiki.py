import requests

def crawl_tiki_category(category_id=8322, limit=50):
    url = "https://tiki.vn/api/v2/products"

    params = {
        "limit": limit,
        "page": 1,
        "category": category_id,
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    print(f"[START] Crawling category {category_id}...")

    resp = requests.get(url, headers=headers, params=params)

    if resp.status_code != 200:
        print("HTTP ERROR:", resp.status_code, resp.text[:200])
        return []

    data = resp.json()
    products = data.get("data", [])

    print(f"[DONE] Got {len(products)} products.")

    # In thử tên sản phẩm
    for p in products:
        print("-", p.get("name"))

    return products


# RUN
crawl_tiki_category(8322, limit=50)
