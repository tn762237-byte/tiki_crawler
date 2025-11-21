pip install requests
import requests
import time
import csv
import random
from datetime import datetime

# --- CẤU HÌNH ---
# 1. User-Agent (Giả lập trình duyệt thật để tránh bị chặn)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://tiki.vn/',
    'Accept': 'application/json'
}

# 2. Ngày cần lấy dữ liệu (Năm-Tháng-Ngày)
# LƯU Ý: Hãy đổi thành ngày gần nhất để test (ví dụ ngày hôm qua) vì 5/9/2025 chưa đến.
TARGET_DATE_STR = "2025-09-05" 
CATEGORY_ID = 8322 # Nhà sách Tiki

# Chuyển đổi ngày mục tiêu
target_date = datetime.strptime(TARGET_DATE_STR, "%Y-%m-%d").date()

def get_product_date(product_id):
    """
    Hàm gọi API chi tiết để lấy ngày tạo sản phẩm
    Vì API Listing thường không có ngày chính xác.
    """
    url = f"https://tiki.vn/api/v2/products/{product_id}"
    try:
        # Sleep ngẫu nhiên để không bị chặn khi gọi liên tục
        time.sleep(random.uniform(0.5, 1.5)) 
        
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            data = response.json()
            # Tiki dùng inventory_type hoặc created_at
            # Ưu tiên lấy created_at (ngày tạo) hoặc updated_at (ngày cập nhật)
            timestamp = data.get('created_at')
            if timestamp:
                return datetime.fromtimestamp(timestamp).date()
    except Exception:
        pass
    return None

def crawl_data():
    page = 1
    results = []
    stop_crawling = False

    print(f"🚀 Bắt đầu crawl dữ liệu ngày: {target_date}")

    while not stop_crawling:
        # sort=newest để đảm bảo lấy hàng mới nhất trước
        url = f"https://tiki.vn/api/v2/listings?limit=40&include=advertisement&category={CATEGORY_ID}&page={page}&sort=newest"
        
        try:
            print(f"--> Đang tải danh sách trang {page}...")
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ Lỗi API Listing: {response.status_code}")
                break

            data = response.json()
            items = data.get('data', [])

            if not items:
                print("⚠️ Hết sản phẩm. Dừng.")
                break

            for item in items:
                p_id = item.get('id')
                p_name = item.get('name')
                p_price = item.get('price')

                # Gọi hàm lấy ngày chi tiết (Quan trọng)
                p_date = get_product_date(p_id)

                if p_date:
                    print(f"   Checking: {p_name[:30]}... | Ngày: {p_date}")
                    
                    if p_date == target_date:
                        # 1. Đúng ngày -> Lưu
                        results.append({
                            'id': p_id,
                            'name': p_name,
                            'price': p_price,
                            'date': str(p_date),
                            'url': f"https://tiki.vn/{item.get('url_path')}"
                        })
                        print("   ✅ ĐÃ LẤY!")

                    elif p_date < target_date:
                        # 2. Gặp ngày cũ hơn -> Dừng tool
                        print(f"🛑 Đã gặp ngày cũ hơn ({p_date}). Dừng toàn bộ.")
                        stop_crawling = True
                        break
                    
                    # 3. Nếu p_date > target_date (ngày tương lai/mới hơn) -> Tiếp tục
                else:
                    print(f"   ⚠️ Không lấy được ngày của ID {p_id}")

            page += 1
            time.sleep(1) # Nghỉ giữa các trang

        except Exception as e:
            print(f"❌ Lỗi hệ thống: {e}")
            break
            
    return results

if __name__ == "__main__":
    data = crawl_data()
    
    # Lưu file CSV
    filename = "ket_qua_tiki.csv"
    if data:
        keys = data[0].keys()
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        print(f"\n🎉 Hoàn tất! Đã lưu {len(data)} dòng vào {filename}")
    else:
        # Tạo file rỗng hoặc ghi log nếu không có dữ liệu để Github không báo lỗi file thiếu
        with open(filename, 'w') as f:
            f.write("Khong co du lieu trung khop")
        print("\n⚠️ Không tìm thấy dữ liệu nào khớp ngày yêu cầu.")
