# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, jsonify, request
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from bs4 import BeautifulSoup
import time
import random
import re
from urllib.parse import urljoin
from datetime import datetime
import traceback

# [v28.0] 引入終極破甲套件
import cloudscraper 

app = Flask(__name__)
auth = HTTPBasicAuth()

# ==========================================
# 🎨 [HTML 模板區]
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yahoo 汽車爬蟲 v28.0</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
    <style>
        body { padding: 20px; background-color: #f4f6f9; font-family: "Microsoft JhengHei", sans-serif; }
        .card { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .brand-grid { max-height: 200px; overflow-y: auto; border: 1px solid #dee2e6; padding: 10px; border-radius: 5px; background: #fff; }
        .form-check { margin-bottom: 5px; margin-right: 15px; display: inline-block; min-width: 140px; }
        .price-tag { color: #e63946; font-weight: bold; font-size: 1.05rem; }
        .fuel-tag { color: #d35400; font-weight: bold; }
        .ev-tag { color: #198754; font-weight: bold; } 
        #statusMsg { font-weight: bold; color: #555; }
        .year-selector { background: #e9ecef; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
    </style>
</head>
<body>
<div class="container-fluid">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2 class="fw-bold mb-0">🏎️ Yahoo 汽車超級比較器 <span class="badge bg-dark">v28.0 突破封鎖版</span></h2>
        <button id="btnExport" class="btn btn-outline-success" disabled>📥 下載 Excel</button>
    </div>
    
    <div class="card p-4">
        <div class="row">
            <div class="col-md-9">
                <h5 class="fw-bold mb-3">1. 選擇品牌 (可多選)</h5>
                <div class="mb-2">
                    <button class="btn btn-sm btn-outline-secondary me-2" id="selectAll">全選</button>
                    <button class="btn btn-sm btn-outline-secondary" id="deselectAll">取消全選</button>
                </div>
                <div class="brand-grid" id="brandContainer">
                    <div class="text-center text-muted">載入品牌列表...</div>
                </div>
            </div>
            
            <div class="col-md-3">
                <h5 class="fw-bold mb-3">2. 選擇年份</h5>
                <div class="year-selector">
                    {% for y in years %}
                    <div class="form-check">
                        <input class="form-check-input year-chk" type="checkbox" value="{{ y }}" id="year_{{ y }}" {% if loop.index <= 4 %}checked{% endif %}>
                        <label class="form-check-label" for="year_{{ y }}">{{ y }}</label>
                    </div>
                    {% endfor %}
                </div>
                
                <div class="d-grid gap-2">
                    <button id="btnStart" class="btn btn-success btn-lg" disabled>3. 開始分析</button>
                </div>
                <div class="mt-2 text-center">
                    <span id="statusMsg" class="small">請先勾選品牌</span>
                </div>
            </div>
        </div>
        
        <div class="progress mt-3" style="display:none; height: 25px;">
            <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%">0%</div>
        </div>
    </div>

    <div class="card p-4">
        <table id="carTable" class="table table-hover align-middle" style="width:100%">
            <thead>
                <tr>
                    <th>年份</th><th>品牌</th><th>車型 (Trim)</th>
                    <th>售價</th><th>排氣量</th><th>引擎型式</th>
                    <th>馬力</th><th>扭力</th><th>能耗 (油/電)</th>
                    <th>變速箱</th><th>連結</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>
</div>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
<script>
    let table;
    let queue = [];
    let totalItems = 0;
    let processedItems = 0;
    $(document).ready(function() {
        table = $('#carTable').DataTable({
            language: { url: "//cdn.datatables.net/plug-ins/1.11.5/i18n/zh-HANT.json" },
            order: [[3, 'asc']],
            columns: [
                { data: 'year' }, { data: 'brand' }, { data: 'model' },
                { data: 'price_val', render: (d, t, r) => t === 'display' ? `<span class="price-tag">${r.price}</span>` : d },
                { data: 'displacement_val', render: (d, t, r) => t === 'display' ? r.displacement : d },
                { data: 'engine_type' },
                { data: 'horsepower_val', render: (d, t, r) => t === 'display' ? `<span class="text-primary fw-bold">${r.horsepower}</span>` : d },
                { data: 'torque_val', render: (d, t, r) => t === 'display' ? r.torque : d },
                { data: 'fuel_val', render: (d, t, r) => {
                        if (t === 'display') {
                            if (r.is_ev) return `<span class="ev-tag">${r.fuel}</span>`;
                            return `<span class="fuel-tag">${r.fuel}</span>`;
                        }
                        return d;
                    }
                },
                { data: 'transmission' },
                { data: 'url', render: d => `<a href="${d}" target="_blank" class="btn btn-sm btn-outline-secondary">Go</a>` }
            ]
        });
        $.get('/api/brands', function(data) {
            let html = '';
            data.forEach(b => {
                html += `<div class="form-check"><input class="form-check-input brand-chk" type="checkbox" value="${b.url}" id="chk_${b.name}"><label class="form-check-label" for="chk_${b.name}">${b.name}</label></div>`;
            });
            $('#brandContainer').html(html);
        });
        
        $(document).on('change', '.brand-chk, .year-chk', function() { updateStartButton(); });
        $('#selectAll').click(function() { $('.brand-chk').prop('checked', true); updateStartButton(); });
        $('#deselectAll').click(function() { $('.brand-chk').prop('checked', false); updateStartButton(); });
        
        function updateStartButton() {
            let brandCount = $('.brand-chk:checked').length;
            let yearCount = $('.year-chk:checked').length;
            
            if(brandCount > 0 && yearCount > 0) {
                $('#btnStart').prop('disabled', false).text(`3. 開始分析 (${brandCount} 品牌)`);
                $('#statusMsg').text('準備就緒');
            } else {
                $('#btnStart').prop('disabled', true).text('3. 開始分析');
                if (brandCount === 0) $('#statusMsg').text('請勾選至少一個品牌');
                else if (yearCount === 0) $('#statusMsg').text('請勾選至少一個年份');
            }
        }
        
        $('#btnStart').click(async function() {
            let selectedBrands = $('.brand-chk:checked').map(function() { return $(this).val(); }).get();
            let selectedYears = $('.year-chk:checked').map(function() { return $(this).val(); }).get();
            
            if(selectedBrands.length === 0 || selectedYears.length === 0) return;
            
            table.clear().draw();
            queue = [];
            totalItems = 0;
            processedItems = 0;
            updateProgress(0);
            $('.progress').show();
            $('#btnStart').prop('disabled', true);
            $('#btnExport').prop('disabled', true);
            $('#statusMsg').html('<span class="text-danger">正在掃描...</span>');
            
            for(let i=0; i<selectedBrands.length; i++) {
                try {
                    let urls = await $.get('/api/get_brand_urls', { 
                        url: selectedBrands[i],
                        years: selectedYears.join(',') 
                    });
                    queue = queue.concat(urls);
                    $('#statusMsg').text(`掃描進度: ${i+1}/${selectedBrands.length} 品牌...`);
                } catch(e) {}
            }
            totalItems = queue.length;
            if(totalItems === 0) {
                $('#statusMsg').text('無符合車款。');
                $('#btnStart').prop('disabled', false);
                return;
            }
            $('#statusMsg').html(`<span class="text-primary">抓取 ${totalItems} 台車規格中...</span>`);
            processQueue(); processQueue(); processQueue();
        });
        $('#btnExport').click(function() {
            let data = table.rows().data().toArray();
            if(data.length === 0) return;
            let exportData = data.map(row => ({
                "年份": row.year,
                "品牌": row.brand,
                "車型": row.model,
                "售價(萬)": row.price_val,
                "排氣量(cc)": row.displacement_val > 0 ? row.displacement_val : "",
                "引擎型式": row.engine_type,
                "馬力(hp)": row.horsepower_val,
                "扭力(kgm)": row.torque_val,
                "能耗": row.fuel,
                "類型": row.is_ev ? "電動車" : "燃油/油電",
                "變速箱": row.transmission,
                "連結": row.url
            }));
            let wb = XLSX.utils.book_new();
            let ws = XLSX.utils.json_to_sheet(exportData);
            XLSX.utils.book_append_sheet(wb, ws, "車款資料");
            let fileName = `Car_Specs_${new Date().toISOString().slice(0,10)}.xlsx`;
            XLSX.writeFile(wb, fileName);
        });
    });
    function processQueue() {
        if(queue.length === 0) {
            if(processedItems >= totalItems && totalItems > 0) {
                $('#statusMsg').html('<span class="text-success"><strong>✨ 完成！</strong></span>');
                $('#btnStart').prop('disabled', false);
                $('#btnExport').prop('disabled', false);
            }
            return;
        }
        let url = queue.shift();
        $.get('/api/scrape_one', { url: url }, function(data) {
            if(!data.error) table.row.add(data).draw(false);
            processedItems++;
            updateProgress();
            setTimeout(processQueue, Math.random() * 1000 + 500);
        }).fail(function() {
            processedItems++; updateProgress(); processQueue();
        });
    }
    function updateProgress(val) {
        if(val === undefined) val = Math.round((processedItems / totalItems) * 100);
        $('#progressBar').css('width', val + '%').text(val + '%');
    }
</script>
</body>
</html>
"""

# ==========================================
# 🔐 [設定區] 帳號密碼
# ==========================================
USERS = {
    "root": generate_password_hash("leon50906")
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and check_password_hash(USERS.get(username), password):
        return username
    return None

# ==========================================
# 爬蟲設定與連線池建立
# ==========================================
# [v28.0] 使用 cloudscraper 取代傳統 requests，完美模擬現代瀏覽器行為
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def get_dynamic_years():
    current_year = datetime.now().year
    return [str(y) for y in range(current_year + 1, current_year - 4, -1)]

FALLBACK_BRANDS = [
    {"name": "Alfa Romeo", "url": "https://autos.yahoo.com.tw/new-cars/make/alfa-romeo"},
    {"name": "Audi", "url": "https://autos.yahoo.com.tw/new-cars/make/audi"},
    {"name": "Bentley", "url": "https://autos.yahoo.com.tw/new-cars/make/bentley"},
    {"name": "BMW", "url": "https://autos.yahoo.com.tw/new-cars/make/bmw"},
    {"name": "Ferrari", "url": "https://autos.yahoo.com.tw/new-cars/make/ferrari"},
    {"name": "Ford", "url": "https://autos.yahoo.com.tw/new-cars/make/ford"},
    {"name": "Foxtron", "url": "https://autos.yahoo.com.tw/new-cars/make/foxtron"},
    {"name": "Honda", "url": "https://autos.yahoo.com.tw/new-cars/make/honda"},
    {"name": "Hyundai", "url": "https://autos.yahoo.com.tw/new-cars/make/hyundai"},
    {"name": "Infiniti", "url": "https://autos.yahoo.com.tw/new-cars/make/infiniti"},
    {"name": "Jaguar", "url": "https://autos.yahoo.com.tw/new-cars/make/jaguar"},
    {"name": "Kia", "url": "https://autos.yahoo.com.tw/new-cars/make/kia"},
    {"name": "Lamborghini", "url": "https://autos.yahoo.com.tw/new-cars/make/lamborghini"},
    {"name": "Land Rover", "url": "https://autos.yahoo.com.tw/new-cars/make/land-rover"},
    {"name": "Lexus", "url": "https://autos.yahoo.com.tw/new-cars/make/lexus"},
    {"name": "Lotus", "url": "https://autos.yahoo.com.tw/new-cars/make/lotus"},
    {"name": "Luxgen", "url": "https://autos.yahoo.com.tw/new-cars/make/luxgen"},
    {"name": "Maserati", "url": "https://autos.yahoo.com.tw/new-cars/make/maserati"},
    {"name": "Mazda", "url": "https://autos.yahoo.com.tw/new-cars/make/mazda"},
    {"name": "McLaren", "url": "https://autos.yahoo.com.tw/new-cars/make/mclaren"},
    {"name": "Mercedes-Benz", "url": "https://autos.yahoo.com.tw/new-cars/make/m-benz"},
    {"name": "MG", "url": "https://autos.yahoo.com.tw/new-cars/make/mg"},
    {"name": "Mini", "url": "https://autos.yahoo.com.tw/new-cars/make/mini"},
    {"name": "Mitsubishi", "url": "https://autos.yahoo.com.tw/new-cars/make/mitsubishi"},
    {"name": "Nissan", "url": "https://autos.yahoo.com.tw/new-cars/make/nissan"},
    {"name": "Opel", "url": "https://autos.yahoo.com.tw/new-cars/make/opel"},
    {"name": "Peugeot", "url": "https://autos.yahoo.com.tw/new-cars/make/peugeot"},
    {"name": "Porsche", "url": "https://autos.yahoo.com.tw/new-cars/make/porsche"},
    {"name": "Rolls-Royce", "url": "https://autos.yahoo.com.tw/new-cars/make/rolls-royce"},
    {"name": "Skoda", "url": "https://autos.yahoo.com.tw/new-cars/make/skoda"},
    {"name": "Subaru", "url": "https://autos.yahoo.com.tw/new-cars/make/subaru"},
    {"name": "Suzuki", "url": "https://autos.yahoo.com.tw/new-cars/make/suzuki"},
    {"name": "Tesla", "url": "https://autos.yahoo.com.tw/new-cars/make/tesla"},
    {"name": "Toyota", "url": "https://autos.yahoo.com.tw/new-cars/make/toyota"},
    {"name": "Volkswagen", "url": "https://autos.yahoo.com.tw/new-cars/make/volkswagen"},
    {"name": "Volvo", "url": "https://autos.yahoo.com.tw/new-cars/make/volvo"}
]

def get_number(text):
    if not text: return 0
    clean = text.replace(',', '')
    match = re.search(r'(\d+(\.\d+)?)', clean)
    if match: return float(match.group(1))
    return 0

def clean_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text.strip())

def hunt_engine_info(soup, raw_specs):
    candidates = [raw_specs.get("engine_general", ""), raw_specs.get("induction", ""), raw_specs.get("cylinders", "")]
    for li in soup.find_all('li'):
        txt = clean_text(li.get_text())
        if any(k in txt for k in ["引擎", "汽缸", "渦輪", "直列", "V型", "水平對臥"]):
            candidates.append(txt)
    full_text = " ".join(candidates)
    
    induction = ""
    if "渦輪" in full_text or "Turbo" in full_text: induction = "渦輪增壓"
    elif "機械增壓" in full_text: induction = "機械增壓"
    elif "純電" in full_text or "馬達" in full_text or raw_specs.get("is_ev"): induction = "電動馬達"
    elif "自然進氣" in full_text or "NA" in full_text: induction = "自然進氣"
    if not induction and raw_specs.get("displacement_val", 0) > 0: induction = "自然進氣"

    cyl = ""
    match_std = re.search(r'(直列\d+缸|V型\d+缸|水平對臥\d+缸|W型\d+缸)', full_text)
    match_cn = re.search(r'(直列[二三四五六八十]+缸|V型[六八十]+缸)', full_text)
    match_simple = re.search(r'(L\d|V\d+|\d+缸)', full_text)
    
    if match_std: cyl = match_std.group(1)
    elif match_cn: cyl = match_cn.group(1)
    elif match_simple:
        val = match_simple.group(1)
        if "L" in val: cyl = f"直列{val.replace('L','')}缸"
        elif "V" in val: cyl = f"V型{val.replace('V','')}缸"
        else: cyl = val

    if induction == "電動馬達": return "純電動馬達"
    parts = [p for p in [induction, cyl] if p]
    return "/".join(parts) if parts else "N/A"

def hunt_ev_range(soup):
    keywords = ["續航", "滿電", "最大里程", "WLTP", "NEDC"]
    exclude_keywords = ["油耗", "公升", "L/100km", "加速", "0-100", "秒"]
    def check_text(txt):
        if not any(k in txt for k in keywords): return None
        if any(bad in txt for bad in exclude_keywords): return None
        if "km" not in txt.lower() and "公里" not in txt: return None
        match = re.search(r'(\d+(\.\d+)?)\s*(?:km|公里)(?!\s*[/hhr小時])', txt, re.IGNORECASE)
        if match: return match.group(1)
        return None
    for li in soup.find_all('li'):
        res = check_text(clean_text(li.get_text()))
        if res: return res
    elements = soup.find_all(string=re.compile(r'(km|公里)'))
    for el in elements:
        if el.parent:
            res = check_text(clean_text(el.parent.get_text()))
            if res: return res
    return None

@app.route('/api/brands')
@auth.login_required
def get_brands():
    return jsonify(sorted(FALLBACK_BRANDS, key=lambda x: x['name']))

@app.route('/api/get_brand_urls')
@auth.login_required
def get_brand_urls():
    brand_url = request.args.get('url')
    years_str = request.args.get('years')
    
    if not brand_url: return jsonify([])
    
    if years_str:
        target_years = years_str.split(',')
    else:
        target_years = get_dynamic_years()[:4]

    try:
        brand_slug = brand_url.rstrip('/').split('/')[-1].lower()
        if brand_slug == 'mercedes-benz': brand_slug = 'm-benz'
    except: brand_slug = ""
    
    urls_to_scrape = []
    
    try:
        # [v28.0] 使用 scraper 取代 requests，突破防護
        resp = scraper.get(brand_url, timeout=15)
        
        # 加上日誌，如果仍然被擋，我們可以看到原因
        if resp.status_code != 200:
            print(f"⚠️ 警告: Yahoo 首頁抓取失敗，狀態碼: {resp.status_code}")
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        base_models = set()
        
        for link in soup.find_all('a', href=re.compile(r'/new-cars/model/')):
            href = link['href']
            full_url = urljoin("https://autos.yahoo.com.tw", href)
            match = re.search(r'-(20\d{2})$', full_url)
            if match:
                base_url = full_url[:match.start()]
                base_models.add(base_url)
            else:
                base_models.add(full_url)
        
        final_model_urls = set()
        
        for base_url in base_models:
            for year in target_years:
                guess_url = f"{base_url}-{year}"
                if guess_url not in final_model_urls:
                    try:
                        # [v28.0] 使用 scraper 進行暴力測試
                        check = scraper.get(guess_url, timeout=5)
                        if check.status_code == 200:
                            final_model_urls.add(guess_url)
                    except: pass

        for m_url in final_model_urls:
            try:
                time.sleep(random.uniform(0.1, 0.3)) # 稍微放慢一點避免被抓
                m_resp = scraper.get(m_url, timeout=15)
                m_soup = BeautifulSoup(m_resp.text, 'html.parser')
                for t_link in m_soup.find_all('a', href=re.compile(r'/new-cars/trim/')):
                    t_href = t_link['href']
                    if brand_slug and brand_slug not in t_href.lower(): continue
                    t_url = urljoin("https://autos.yahoo.com.tw", t_href)
                    if t_url not in urls_to_scrape: urls_to_scrape.append(t_url)
            except: pass
            
        return jsonify(urls_to_scrape)
    except Exception as e: 
        print(f"❌ 解析品牌 URL 發生錯誤: {e}")
        return jsonify([])

def extract_price_data(soup):
    price_text, price_val = "N/A", 0
    try:
        found = False
        for keyword in ["牌照稅", "燃料稅"]:
            if found: break
            for el in soup.find_all(string=re.compile(keyword)):
                if el.parent.parent:
                    full_text = clean_text(el.parent.parent.get_text())
                    if "未公布" in full_text or "電洽" in full_text or "即將上市" in full_text: return "N/A", 0
                    if keyword in full_text:
                        matches = re.findall(r'(\d{2,5}(\.\d+)?)', full_text.split(keyword)[0])
                        if matches: 
                            val = float(matches[-1][0])
                            if val > 10: price_val = val; price_text = f"{val} 萬"; found = True; break
        if not found:
            for key in ["建議售價", "售價", "牌價"]:
                target = soup.find(string=re.compile(key))
                if target:
                    container = target.parent.parent
                    full_text = clean_text(container.get_text())
                    if "未公布" in full_text or "電洽" in full_text or "即將上市" in full_text: return "N/A", 0
                    match = re.search(r'(\d{2,5}(\.\d+)?)', full_text.replace(key, ""))
                    if match: 
                        val = float(match.group(1))
                        if val > 10: price_val = val; price_text = f"{val} 萬"; break
    except: pass
    return price_text, price_val

def extract_hp_torque(text):
    hp_txt, torque_txt = "N/A", "N/A"
    hp_val, torque_val = 0, 0
    
    hp_match = re.search(r'(\d+(\.\d+)?)\s*(?:hp|ps|bhp)', text, re.IGNORECASE)
    if hp_match:
        hp_val = float(hp_match.group(1))
        hp_txt = f"{hp_val} hp"

    torque_match = re.search(r'(\d+(\.\d+)?)\s*(?:kgm|Nm)', text, re.IGNORECASE)
    if torque_match:
        torque_val = float(torque_match.group(1))
        torque_txt = f"{torque_val} kgm"

    sys_hp_match = re.search(r'(?:總輸出|綜效|系統).*?(\d+(\.\d+)?)\s*(?:hp|ps|bhp)', text, re.IGNORECASE)
    if sys_hp_match:
        sys_hp = float(sys_hp_match.group(1))
        if sys_hp > 0:
            hp_val = sys_hp
            hp_txt = f"{sys_hp} hp (綜效)"
    
    sys_torque_match = re.search(r'(?:總輸出|綜效|系統).*?(\d+(\.\d+)?)\s*(?:kgm|Nm)', text, re.IGNORECASE)
    if sys_torque_match:
        sys_torque = float(sys_torque_match.group(1))
        torque_val = sys_torque
        torque_txt = f"{sys_torque} kgm (綜效)"

    return hp_txt, hp_val, torque_txt, torque_val

def extract_fuel_basic(label, value):
    if "油耗" in label or "能量" in label:
        match = re.search(r'(\d+(\.\d+)?)', value)
        if match:
            val_lower = value.lower()
            if "km/ltr" in val_lower or "km/l" in val_lower: return f"{match.group(1)} km/L", float(match.group(1))
    return None, 0

@app.route('/api/scrape_one')
@auth.login_required
def scrape_one():
    url = request.args.get('url')
    if not url: return jsonify({"error": "no url"})
    try:
        # [v28.0] 單車抓取也改用 scraper
        response = scraper.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('h1')
        full_title = clean_text(title_tag.text) if title_tag else "未知"
        parts = full_title.split(' ')
        year, brand, model = (parts[0], parts[1], " ".join(parts[2:])) if len(parts)>2 else ("", "", full_title)
        price_text, price_val = extract_price_data(soup)
        specs = {"induction": "", "cylinders": "", "engine_general": "", "displacement": "N/A", "displacement_val": 0, "trans": "N/A", "power": "N/A", "power_val": 0, "torque": "N/A", "torque_val": 0, "fuel": "N/A", "fuel_val": 0, "is_ev": False}
        for item in soup.find_all('li'):
            full_text = clean_text(item.get_text())
            spans = item.find_all(['span', 'div'])
            label = clean_text(spans[0].get_text()) if len(spans) >= 2 else ""
            value = clean_text(spans[1].get_text()) if len(spans) >= 2 else ""
            if "進氣型式" in label: specs["induction"] = value
            elif "汽缸設計" in label: specs["cylinders"] = value
            elif "引擎型式" in label: specs["engine_general"] = value 
            elif "排氣量" in label: specs["displacement"] = value; specs["displacement_val"] = get_number(value)
            elif "變速系統" in label: specs["trans"] = value
            elif "最大馬力" in label: specs["power"] = value; specs["power_val"] = get_number(value)
            elif "最大扭力" in label: specs["torque"] = value; specs["torque_val"] = get_number(value)
            e_txt, e_val = extract_fuel_basic(label, value)
            if e_txt: specs["fuel"] = e_txt; specs["fuel_val"] = e_val
            if "性能數據" in full_text:
                h_t, h_v, t_t, t_v = extract_hp_torque(full_text)
                if h_t != "N/A": specs["power"] = h_t; specs["power_val"] = h_v
                if t_t != "N/A": specs["torque"] = t_t; specs["torque_val"] = t_v
        ev_range = hunt_ev_range(soup)
        if ev_range and (specs["displacement_val"] == 0 or specs["fuel_val"] == 0): specs["fuel"] = f"{ev_range} km"; specs["fuel_val"] = float(ev_range); specs["is_ev"] = True
        final_engine = hunt_engine_info(soup, specs)
        return jsonify({
            "year": year, "brand": brand, "model": model, "price": price_text, "price_val": price_val, "engine_type": final_engine, "displacement": specs["displacement"], "displacement_val": specs["displacement_val"], "transmission": specs["trans"], "horsepower": specs["power"], "horsepower_val": specs["power_val"], "torque": specs["torque"], "torque_val": specs["torque_val"], "fuel": specs["fuel"], "fuel_val": specs["fuel_val"], "is_ev": specs["is_ev"], "url": url
        })
    except Exception as e: return jsonify({"error": str(e)})

@app.route('/')
@auth.login_required
def index():
    years = get_dynamic_years()
    return render_template_string(HTML_TEMPLATE, years=years)

if __name__ == '__main__':
    print("=================================================")
    print("🚗 Yahoo 汽車超級比較器 - NAS Secure 版 v28.0 (突破封鎖)")
    print("服務啟動中...")
    print("=================================================")
    try:
        app.run(debug=False, port=5000, host='0.0.0.0')
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        traceback.print_exc()
