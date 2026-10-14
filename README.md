# Yahoo 汽車超級比較器

從 [Yahoo 奇摩汽車](https://autos.yahoo.com.tw)（新車資料）抓取各品牌、各年份的車款規格，整理成可排序、可篩選的表格，並能匯出 Excel。以 Flask 寫成的單檔網頁應用（`app.py`），用 Docker 部署。

## 功能

- 選擇品牌（36 個）與年份（明年～大前年，依伺服器日期自動更新），一次比較多個車款
- 擷取欄位：價格、引擎類型、排氣量、變速箱、馬力、扭力、油耗／電耗等
- 下載 Excel（`Car_Specs_YYYY-MM-DD.xlsx`，在瀏覽器端產生）
- 失敗項目可一鍵重試
- 快取快照：把抓過的資料存成 JSON 快照，之後可載入並只補抓新的品牌／年份，不必重爬
- HTTP Basic Auth 登入保護

## 快速開始（Docker）

```bash
cp .env.example .env      # 然後編輯 .env 填入帳密
docker compose up -d --build
```

開啟 <http://localhost:5520>，輸入 `.env` 裡設定的帳密即可。

> `docker-compose.yml` 將容器的 5000 port 對應到主機 5520，並掛載 `./data` 保存快照（重建容器也不會消失）。

## 設定

設定皆透過環境變數（Docker 下寫在 `.env`，已被 `.gitignore` 排除，請勿提交）：

| 變數 | 必填 | 說明 |
| --- | --- | --- |
| `APP_USER` / `APP_PASSWORD` | 是（或用 `APP_USERS`） | 單一帳號。密碼可含任意字元 |
| `APP_USERS` | 否 | 多帳號：`帳號1:密碼1,帳號2:密碼2`，密碼不可含逗號 |
| `PORT` | 否 | 監聽 port，預設 `5000` |
| `DATA_DIR` | 否 | 快照資料夾，預設 `./data` |

`.env` 注意事項：值不要加引號，密碼避免使用 `$` 和 `#`。未設定任何帳密時程式會直接結束。

## 不用 Docker 執行

需要 Python 3.9+：

```bash
pip install -r requirements.txt
export APP_USER=admin APP_PASSWORD=your-password   # Windows PowerShell: $env:APP_USER="admin"
python app.py
```

預設以 waitress 監聽 `0.0.0.0:5000`（找不到 waitress 時退回 Flask 內建伺服器）。

## 運作方式

爬取分三步，由前端依序呼叫，每一步都是獨立請求，因此失敗可以個別重試：

1. `GET /api/brand_models`：讀品牌頁，回傳要掃描的「車系＋年份」頁面清單
2. `GET /api/model_trims`：讀單一「車系＋年份」頁，回傳該車系的車款（trim）網址；該年份不存在（404）則回傳空清單
3. `GET /api/scrape_one`：讀單一車款規格頁並解析成結構化資料

對外請求以 `cloudscraper` 發送，所有執行緒共用節流（任兩個請求至少間隔 0.25～0.6 秒），失敗時自動重試；只允許連到 `autos.yahoo.com.tw`，轉址到其他網域會被拒絕。

### 其他 API

| 路徑 | 說明 |
| --- | --- |
| `GET /api/brands` | 品牌清單 |
| `GET /api/snapshots` | 列出所有快照 |
| `GET /api/snapshots/<id>` | 讀取單一快照 |
| `POST /api/snapshots` | 將新抓到的資料與已完整掃描的品牌年份，合併進基底快照後存成一份**新**快照 |

所有路徑都需要 Basic Auth。

### 快照

快照存放於 `data/snapshots/<YYYYMMDD_HHMMSS>.json`，只新增、不覆蓋、不刪除（基底快照不會被改動）。要清理請直接手動刪除檔案。

## 專案結構

```
app.py              # 後端 API、爬蟲解析、前端 HTML 模板（全部在同一檔）
requirements.txt    # Python 相依套件
Dockerfile
docker-compose.yml
.env.example        # 環境變數範本
data/               # 執行時產生的快照（不進 git）
```

`yahoo-car-scraper-backup-20260930/` 為舊版備份。

## 注意事項

- 本工具抓取公開網頁內容，請自行控制使用頻率並遵守 Yahoo 奇摩的使用條款
- 頁面結構改變或被對方擋下時，抓取會失敗並在 log 中記錄原因（例如 `HTTP 403`、隱私同意頁）
- 對外服務時請務必設定強密碼，並建議放在 HTTPS 反向代理之後（Basic Auth 以明文傳送帳密）
