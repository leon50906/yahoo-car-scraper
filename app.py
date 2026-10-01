# -*- coding: utf-8 -*-
import hmac
import json
import logging
import os
import random
import re
import threading
import time
from datetime import datetime
from urllib.parse import unquote, urljoin, urlparse

import cloudscraper
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template_string, request
from flask_httpauth import HTTPBasicAuth

VERSION = "v30.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yahoo-car")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # 快照上傳上限
auth = HTTPBasicAuth()

# ==========================================
# 🎨 [HTML 模板區]
# ==========================================
HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Yahoo 汽車爬蟲 {{ version }}</title>
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
        <h2 class="fw-bold mb-0">🏎️ Yahoo 汽車超級比較器 <span class="badge bg-dark">{{ version }}</span></h2>
        <div>
            <button id="btnRetry" class="btn btn-outline-danger me-2" style="display:none">🔁 重試失敗項目</button>
            <button id="btnExport" class="btn btn-outline-success" disabled>📥 下載 Excel</button>
        </div>
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
                        <input class="form-check-input year-chk" type="checkbox" value="{{ y }}" id="year_{{ y }}" {% if y == current_year %}checked{% endif %}>
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

        <div class="mt-3">
            <h5 class="fw-bold mb-2">快取（快照只新增、不覆蓋）</h5>
            <div class="d-flex flex-wrap align-items-center gap-2">
                <select id="snapSelect" class="form-select form-select-sm" style="max-width: 480px;"></select>
                <button id="btnLoad" class="btn btn-sm btn-outline-primary">📂 載入</button>
                <button id="btnSave" class="btn btn-sm btn-outline-primary" disabled>💾 存成快照</button>
                <div class="form-check mb-0"><input class="form-check-input" type="checkbox" id="chkForce"><label class="form-check-label" for="chkForce">強制重新抓取所選範圍</label></div>
                <div class="form-check mb-0"><input class="form-check-input" type="checkbox" id="chkAutoSave" checked><label class="form-check-label" for="chkAutoSave">抓完自動存成新快照</label></div>
            </div>
            <div id="cacheInfo" class="small text-muted mt-1">選擇快照後，已掃描過的品牌＋年份直接讀快取，只會去抓沒有的部分。</div>
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
    const YAHOO_ORIGIN = 'https://autos.yahoo.com.tw/';
    const CONCURRENCY = 3;
    let table;
    let seenTrims = new Set();
    let failed = { brands: [], pages: [], trims: [] };
    let running = false;
    // 快取狀態
    let baseId = null;                 // 目前作為基底的快照 id（存檔時會以它為基礎合併成新快照）
    let pending = new Set();           // 本次要抓、尚未完整成功的 "品牌|年份"
    let unsavedRows = [];              // 新抓到、尚未存進快照的列
    let unsavedCombos = new Set();     // 已完整成功、尚未存進快照的 "品牌|年份"
    let lastForce = false;

    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const api = (path, params) => $.getJSON(path, params);
    const comboKey = (slug, year) => `${slug}|${year}`;

    function setStatus(html) { $('#statusMsg').html(html); }
    function updateProgress(done, total) {
        const val = total > 0 ? Math.round(done / total * 100) : 0;
        $('#progressBar').css('width', val + '%').text(val + '%');
    }

    // 以固定並行數處理清單
    async function pool(items, worker) {
        let idx = 0;
        async function loop() {
            while (idx < items.length) {
                const item = items[idx++];
                await worker(item);
                await sleep(Math.random() * 300 + 100);
            }
        }
        const runners = [];
        for (let i = 0; i < Math.min(CONCURRENCY, items.length); i++) runners.push(loop());
        await Promise.all(runners);
    }

    function updateStartButton(keepStatus) {
        const brandCount = $('.brand-chk:checked').length;
        const yearCount = $('.year-chk:checked').length;
        if (running) return;
        if (brandCount > 0 && yearCount > 0) {
            $('#btnStart').prop('disabled', false).text(`3. 開始分析 (${brandCount} 品牌)`);
            if (keepStatus !== true) $('#statusMsg').text('準備就緒');
        } else {
            $('#btnStart').prop('disabled', true).text('3. 開始分析');
            if (keepStatus !== true) $('#statusMsg').text(brandCount === 0 ? '請勾選至少一個品牌' : '請勾選至少一個年份');
        }
    }

    function updateSaveButton() {
        $('#btnSave').prop('disabled', running || (unsavedRows.length === 0 && unsavedCombos.size === 0));
    }

    // ---------- 快照 ----------
    function snapLabel(s) {
        const t = s.created_at ? s.created_at.replace('T', ' ').slice(0, 16) : s.id;
        return `${t} ・ ${s.rows} 台 ・ ${s.combos} 組${s.incomplete ? ' ・ ⚠️不完整' : ''}${s.note ? ' ・ ' + s.note : ''}`;
    }

    async function refreshSnapshots(selectId) {
        let list = [];
        try { list = await api('/api/snapshots'); } catch (e) { $('#cacheInfo').text('無法讀取快照清單'); }
        const sel = $('#snapSelect').empty();
        sel.append($('<option>').val('').text('（不使用快取）'));
        list.forEach(s => sel.append($('<option>').val(s.id).text(snapLabel(s))));
        sel.val(selectId !== undefined ? selectId : (list.length ? list[0].id : ''));
    }

    // 把「新抓到的列＋已完整成功的品牌年份」存成新快照（基底快照不會被改動）
    async function saveSnapshot() {
        if (unsavedRows.length === 0 && unsavedCombos.size === 0) return false;
        const body = {
            base: baseId,
            rows: unsavedRows,
            coverage: [...unsavedCombos].map(k => { const p = k.split('|'); return { brand: p[0], year: parseInt(p[1], 10) }; }),
            incomplete: pending.size > 0,
            note: lastForce ? '強制重抓' : '補抓'
        };
        try {
            const res = await $.ajax({ url: '/api/snapshots', method: 'POST', contentType: 'application/json', data: JSON.stringify(body), dataType: 'json' });
            unsavedRows = [];
            unsavedCombos = new Set();
            baseId = res.id;
            await refreshSnapshots(res.id);
            return res;
        } catch (e) {
            return false;
        }
    }

    // ---------- 抓取：品牌 -> 車系頁 -> 各車款規格 ----------
    async function run(brandJobs, pageJobs, trimJobs) {
        running = true;
        $('#btnStart, #btnExport, #btnRetry, #btnLoad, #btnSave').prop('disabled', true);
        $('.progress').show();
        const newFailed = { brands: [], pages: [], trims: [] };
        pageJobs = pageJobs.slice();
        trimJobs = trimJobs.slice();

        for (let i = 0; i < brandJobs.length; i++) {
            const job = brandJobs[i];
            setStatus(`<span class="text-danger">掃描品牌 ${i + 1}/${brandJobs.length}...</span>`);
            updateProgress(i, brandJobs.length);
            try {
                const d = await api('/api/brand_models', { slug: job.slug, years: job.years.join(',') });
                d.pages.forEach(p => pageJobs.push({ url: p.url, brand: job.slug, year: p.year }));
            } catch (e) {
                newFailed.brands.push(job);
            }
        }

        let done = 0;
        await pool(pageJobs, async job => {
            try {
                const d = await api('/api/model_trims', { url: job.url });
                d.urls.forEach(u => {
                    if (!seenTrims.has(u)) { seenTrims.add(u); trimJobs.push({ url: u, brand: job.brand, year: job.year }); }
                });
            } catch (e) {
                newFailed.pages.push(job);
            }
            done++;
            setStatus(`<span class="text-danger">掃描車系 ${done}/${pageJobs.length}...</span>`);
            updateProgress(done, pageJobs.length);
        });

        done = 0;
        updateProgress(0, trimJobs.length);
        await pool(trimJobs, async job => {
            try {
                const d = await api('/api/scrape_one', { url: job.url });
                table.row.add(d).draw(false);
                unsavedRows.push(d);
            } catch (e) {
                newFailed.trims.push(job);
            }
            done++;
            setStatus(`<span class="text-primary">抓取規格 ${done}/${trimJobs.length}...</span>`);
            updateProgress(done, trimJobs.length);
        });

        failed = newFailed;
        // 沒有任何失敗項目的「品牌|年份」才算完整掃描過（失敗的下次會自動補抓）
        const bad = new Set();
        failed.brands.forEach(j => j.years.forEach(y => bad.add(comboKey(j.slug, y))));
        failed.pages.concat(failed.trims).forEach(j => bad.add(comboKey(j.brand, j.year)));
        [...pending].forEach(k => { if (!bad.has(k)) { pending.delete(k); unsavedCombos.add(k); } });

        running = false;
        let saveMsg = '';
        if ($('#chkAutoSave').is(':checked')) {
            setStatus('<span class="text-primary">儲存快照...</span>');
            const res = await saveSnapshot();
            saveMsg = res ? `，已存成新快照 ${esc(res.id)}` : '，<span class="text-danger">快照儲存失敗（可按「存成快照」重試）</span>';
        } else if (unsavedRows.length > 0) {
            saveMsg = '，尚未存檔（可按「存成快照」）';
        }

        const failCount = failed.brands.length + failed.pages.length + failed.trims.length;
        const rows = table.rows().count();
        if (failCount > 0) {
            setStatus(`<span class="text-warning"><strong>完成，但有 ${failCount} 項失敗（可能被 Yahoo 擋），結果不完整</strong></span>${saveMsg}`);
            $('#btnRetry').show().prop('disabled', false);
        } else {
            $('#btnRetry').hide();
            setStatus((rows > 0 ? '<span class="text-success"><strong>✨ 完成！</strong></span>' : '無符合車款。') + saveMsg);
        }
        $('#btnExport').prop('disabled', rows === 0);
        $('#btnLoad').prop('disabled', false);
        updateSaveButton();
        updateStartButton(true);
    }

    $(document).ready(function() {
        table = $('#carTable').DataTable({
            language: { url: "//cdn.datatables.net/plug-ins/1.11.5/i18n/zh-HANT.json" },
            order: [[3, 'asc']],
            columns: [
                { data: 'year', render: $.fn.dataTable.render.text() },
                { data: 'brand', render: $.fn.dataTable.render.text() },
                { data: 'model', render: $.fn.dataTable.render.text() },
                { data: 'price_val', render: (d, t, r) => t === 'display' ? `<span class="price-tag">${esc(r.price)}</span>` : d },
                { data: 'displacement_val', render: (d, t, r) => t === 'display' ? esc(r.displacement) : d },
                { data: 'engine_type', render: $.fn.dataTable.render.text() },
                { data: 'horsepower_val', render: (d, t, r) => t === 'display' ? `<span class="text-primary fw-bold">${esc(r.horsepower)}</span>` : d },
                { data: 'torque_val', render: (d, t, r) => t === 'display' ? esc(r.torque) : d },
                { data: 'fuel_val', render: (d, t, r) => {
                        if (t === 'display') {
                            return `<span class="${r.is_ev ? 'ev-tag' : 'fuel-tag'}">${esc(r.fuel)}</span>`;
                        }
                        return d;
                    }
                },
                { data: 'transmission', render: $.fn.dataTable.render.text() },
                { data: 'url', render: d => d && d.startsWith(YAHOO_ORIGIN) ? `<a href="${esc(d)}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-secondary">Go</a>` : '' }
            ]
        });
        $.get('/api/brands', function(data) {
            let html = '';
            data.forEach((b, i) => {
                html += `<div class="form-check"><input class="form-check-input brand-chk" type="checkbox" value="${esc(b.slug)}" id="chk_${i}"><label class="form-check-label" for="chk_${i}">${esc(b.name)}</label></div>`;
            });
            $('#brandContainer').html(html);
        });
        refreshSnapshots();

        $(document).on('change', '.brand-chk, .year-chk', function() { updateStartButton(); });
        $('#selectAll').click(function() { $('.brand-chk').prop('checked', true); updateStartButton(); });
        $('#deselectAll').click(function() { $('.brand-chk').prop('checked', false); updateStartButton(); });

        $('#btnStart').click(async function() {
            if (running) return;
            const selectedBrands = $('.brand-chk:checked').map(function() { return $(this).val(); }).get();
            const selectedYears = $('.year-chk:checked').map(function() { return $(this).val(); }).get();
            if (selectedBrands.length === 0 || selectedYears.length === 0) return;
            if (unsavedRows.length > 0 && !confirm('目前有尚未存檔的資料，繼續會捨棄這些資料。要繼續嗎？')) return;

            const force = $('#chkForce').is(':checked');
            const sid = $('#snapSelect').val() || '';
            table.clear().draw();
            seenTrims = new Set();
            failed = { brands: [], pages: [], trims: [] };
            pending = new Set();
            unsavedRows = [];
            unsavedCombos = new Set();
            lastForce = force;
            baseId = sid || null;
            $('#btnRetry').hide();
            updateSaveButton();

            let snap = { rows: [], coverage: [] };
            if (sid) {
                setStatus('<span class="text-primary">讀取快照...</span>');
                try {
                    snap = await api('/api/snapshots/' + encodeURIComponent(sid));
                } catch (e) {
                    baseId = null;
                    setStatus('<span class="text-danger">讀取快照失敗，未開始抓取</span>');
                    return;
                }
            }

            // 已掃描過的「品牌|年份」直接用快取；其餘（或強制重抓時全部）才去抓
            const covered = new Set((snap.coverage || []).map(c => comboKey(c.brand, c.year)));
            const hitKeys = new Set();
            const need = {};
            let missCount = 0;
            selectedBrands.forEach(slug => selectedYears.forEach(y => {
                const k = comboKey(slug, y);
                if (!force && covered.has(k)) {
                    hitKeys.add(k);
                } else {
                    missCount++;
                    pending.add(k);
                    (need[slug] = need[slug] || []).push(y);
                }
            }));
            const cachedRows = (snap.rows || []).filter(r => hitKeys.has(comboKey(r.brand_slug, r.year)));
            cachedRows.forEach(r => seenTrims.add(r.url));
            if (cachedRows.length > 0) table.rows.add(cachedRows).draw();
            $('#cacheInfo').text(sid
                ? `快取命中 ${hitKeys.size} 組（${cachedRows.length} 台），需抓取 ${missCount} 組${force ? '（強制重抓）' : ''}`
                : `未使用快取，需抓取 ${missCount} 組`);

            if (missCount === 0) {
                setStatus(cachedRows.length > 0 ? '<span class="text-success"><strong>✨ 全部來自快取，未連線 Yahoo</strong></span>' : '無符合車款。');
                $('#btnExport').prop('disabled', cachedRows.length === 0);
                return;
            }
            await run(Object.keys(need).map(slug => ({ slug: slug, years: need[slug] })), [], []);
        });

        $('#btnRetry').click(async function() {
            if (running) return;
            await run(failed.brands, failed.pages, failed.trims);
        });

        $('#btnSave').click(async function() {
            if (running) return;
            $(this).prop('disabled', true);
            const res = await saveSnapshot();
            setStatus(res ? `<span class="text-success">已存成新快照 ${esc(res.id)}</span>` : '<span class="text-danger">快照儲存失敗</span>');
            updateSaveButton();
        });

        // 載入：把整份快照顯示出來，並以它作為之後查詢的基底（快照本身不會被改動）
        $('#btnLoad').click(async function() {
            if (running) return;
            const sid = $('#snapSelect').val();
            if (!sid) { setStatus('請先在下拉選單選擇一份快照'); return; }
            if (unsavedRows.length > 0 && !confirm('目前有尚未存檔的資料，載入會捨棄這些資料。要繼續嗎？')) return;
            setStatus('<span class="text-primary">讀取快照...</span>');
            try {
                const snap = await api('/api/snapshots/' + encodeURIComponent(sid));
                table.clear();
                table.rows.add(snap.rows).draw();
                seenTrims = new Set(snap.rows.map(r => r.url));
                failed = { brands: [], pages: [], trims: [] };
                pending = new Set();
                unsavedRows = [];
                unsavedCombos = new Set();
                baseId = sid;
                $('#btnRetry').hide();
                $('#cacheInfo').text(`已載入快照：${snap.rows.length} 台、${(snap.coverage || []).length} 組品牌年份${snap.incomplete ? '（⚠️此快照標示為不完整）' : ''}`);
                setStatus('<span class="text-success"><strong>✨ 已載入快照</strong></span>');
                $('#btnExport').prop('disabled', snap.rows.length === 0);
            } catch (e) {
                setStatus('<span class="text-danger">讀取快照失敗</span>');
            }
            updateSaveButton();
        });

        $('#btnExport').click(function() {
            const data = table.rows().data().toArray();
            if (data.length === 0) return;
            const exportData = data.map(row => ({
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
            const wb = XLSX.utils.book_new();
            const ws = XLSX.utils.json_to_sheet(exportData);
            XLSX.utils.book_append_sheet(wb, ws, "車款資料");
            XLSX.writeFile(wb, `Car_Specs_${new Date().toISOString().slice(0, 10)}.xlsx`);
        });
    });
</script>
</body>
</html>
"""

# ==========================================
# 🔐 [設定區] 帳號密碼（由環境變數提供，不寫死在程式碼裡）
#   方式一：APP_USER + APP_PASSWORD（單一帳號，密碼可含任意字元）
#   方式二：APP_USERS="帳號1:密碼1,帳號2:密碼2"（密碼不可含逗號）
# ==========================================
def load_users():
    users = {}
    for pair in os.environ.get("APP_USERS", "").split(","):
        name, sep, password = pair.partition(":")
        if sep and name.strip() and password:
            users[name.strip()] = password
    user, password = os.environ.get("APP_USER"), os.environ.get("APP_PASSWORD")
    if user and password:
        users[user] = password
    return users


USERS = load_users()
if not USERS:
    raise SystemExit("未設定登入帳密：請設定環境變數 APP_USER 與 APP_PASSWORD（或 APP_USERS=帳號:密碼,帳號2:密碼2）")


@auth.verify_password
def verify_password(username, password):
    expected = USERS.get(username or "")
    if expected is not None and hmac.compare_digest(expected.encode("utf-8"), (password or "").encode("utf-8")):
        return username
    return None


# ==========================================
# 品牌與網址規則
# ==========================================
YAHOO_HOST = "autos.yahoo.com.tw"
YAHOO_BASE = "https://" + YAHOO_HOST

BRANDS = [
    ("Alfa Romeo", "alfa-romeo"), ("Audi", "audi"), ("Bentley", "bentley"), ("BMW", "bmw"),
    ("Ferrari", "ferrari"), ("Ford", "ford"), ("Foxtron", "foxtron"), ("Honda", "honda"),
    ("Hyundai", "hyundai"), ("Infiniti", "infiniti"), ("Jaguar", "jaguar"), ("Kia", "kia"),
    ("Lamborghini", "lamborghini"), ("Land Rover", "land-rover"), ("Lexus", "lexus"),
    ("Lotus", "lotus"), ("Luxgen", "luxgen"), ("Maserati", "maserati"), ("Mazda", "mazda"),
    ("McLaren", "mclaren"), ("Mercedes-Benz", "m-benz"), ("MG", "mg"), ("Mini", "mini"),
    ("Mitsubishi", "mitsubishi"), ("Nissan", "nissan"), ("Opel", "opel"), ("Peugeot", "peugeot"),
    ("Porsche", "porsche"), ("Rolls-Royce", "rolls-royce"), ("Skoda", "skoda"), ("Subaru", "subaru"),
    ("Suzuki", "suzuki"), ("Tesla", "tesla"), ("Toyota", "toyota"), ("Volkswagen", "volkswagen"),
    ("Volvo", "volvo"),
]
BRAND_BY_SLUG = {slug: name for name, slug in BRANDS}
MODEL_YEAR_RE = re.compile(r"^(?P<base>.+)-(?P<year>20\d{2})$")


def get_dynamic_years():
    """年份選項：明年、今年、去年、前年、大前年（依伺服器當下日期計算，跨年自動更新）。"""
    current_year = datetime.now().year
    return [str(y) for y in range(current_year + 1, current_year - 4, -1)]


def validate_yahoo_url(raw, path_prefix):
    """只接受 https://autos.yahoo.com.tw 底下、指定路徑開頭的網址（防止 SSRF）。合法回傳正規化網址，否則 None。"""
    if not raw or len(raw) > 500:
        return None
    try:
        parsed = urlparse(raw.strip())
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc != YAHOO_HOST or not parsed.path.startswith(path_prefix):
        return None
    return parsed._replace(fragment="").geturl()


# ==========================================
# 連線層：限速、重試、只跟隨同站轉址
# ==========================================
REQUEST_GAP = (0.25, 0.6)   # 任兩個對外請求的最小間隔（秒），所有執行緒共用
MAX_REDIRECTS = 3
_local = threading.local()
_throttle_lock = threading.Lock()
_next_slot = 0.0


class FetchError(Exception):
    pass


def _session():
    # requests.Session 不保證執行緒安全，每個執行緒各用一個
    s = getattr(_local, "session", None)
    if s is None:
        s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
        _local.session = s
    return s


def _wait_turn():
    global _next_slot
    with _throttle_lock:
        now = time.monotonic()
        start = max(now, _next_slot)
        _next_slot = start + random.uniform(*REQUEST_GAP)
    if start > now:
        time.sleep(start - now)


def fetch(url, retries=2):
    """取得頁面。200/404 回傳 Response；被擋、逾時、異常一律 raise FetchError（含原因，會寫入 log）。"""
    reason = "unknown"
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(random.uniform(2, 4) * attempt)
        _wait_turn()
        try:
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                resp = _session().get(current, timeout=15, allow_redirects=False)
                if resp.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(current, resp.headers.get("Location", ""))
                    nxt = validate_yahoo_url(target, "/")
                    if not nxt:
                        raise FetchError("被轉址到非 Yahoo 汽車的位置: " + urlparse(target).netloc)
                    current = nxt
                    continue
                break
            else:
                raise FetchError("轉址次數過多")
        except FetchError:
            raise
        except requests.RequestException as e:
            reason = type(e).__name__
            continue

        if resp.status_code == 404:
            return resp
        if resp.status_code == 200:
            if re.search(r"privacy choices", resp.text[:5000], re.IGNORECASE):
                raise FetchError("被導向 Yahoo 隱私同意頁（疑似被擋）")
            return resp
        reason = "HTTP %d" % resp.status_code
        if resp.status_code not in (403, 429, 500, 502, 503, 504):
            break
    raise FetchError("%s (%s)" % (reason, unquote(url)))


def error_response(url, err, status=502):
    log.warning("抓取失敗 %s -> %s", unquote(url), err)
    return jsonify({"error": str(err)}), status


# ==========================================
# 解析工具
# ==========================================
def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def fmt_num(v):
    return "%.10g" % v


def get_number(text):
    if not text:
        return 0
    match = re.search(r"(\d+(\.\d+)?)", text.replace(",", ""))
    return float(match.group(1)) if match else 0


def read_spec_pairs(soup):
    """規格區塊是 <li><span>標籤</span><span>內容</span></li>；只讀這種結構，避免掃到頁面上的新聞文字。"""
    specs = {}
    for li in soup.find_all("li"):
        spans = li.find_all("span", recursive=False)
        if len(spans) != 2:
            continue
        label = clean_text(spans[0].get_text())
        if label and label not in specs:
            specs[label] = clean_text(spans[1].get_text())
    return specs


def extract_price(soup):
    """價格在 <h3 class="price"> 的第一個 span（單位：萬）；不做全頁搜尋，避免抓到新聞裡的日圓價格。"""
    h3 = soup.find("h3", class_="price")
    first = h3.find("span") if h3 else None
    if first:
        match = re.search(r"(\d+(?:\.\d+)?)", clean_text(first.get_text()).replace(",", ""))
        if match and float(match.group(1)) > 0:
            val = float(match.group(1))
            return "%s 萬" % fmt_num(val), val
    return "N/A", 0


_HP_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:hp|ps|bhp)", re.IGNORECASE)
_TORQUE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kgm|kg-m|nm)", re.IGNORECASE)


def _first_hp(text):
    m = _HP_RE.search(text)
    return float(m.group(1)) if m else None


def _first_torque_kgm(text):
    m = _TORQUE_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2).lower() == "nm":
        val = round(val / 9.80665, 1)   # 統一成 kgm
    return val


def parse_performance(text):
    """性能數據例：'186hp@6000rpm 22.5kgm@3600~5200rpm 總輸出 230hp'。回傳 (馬力文字, 馬力值, 扭力文字, 扭力值)。"""
    hp, torque = _first_hp(text), _first_torque_kgm(text)
    hp_suffix = torque_suffix = ""
    marker = re.search(r"總輸出|綜效|系統", text)
    if marker:
        tail = text[marker.end():]
        sys_hp, sys_torque = _first_hp(tail), _first_torque_kgm(tail)
        if sys_hp:
            hp, hp_suffix = sys_hp, " (綜效)"
        if sys_torque:
            torque, torque_suffix = sys_torque, " (綜效)"
    hp_txt = "%s hp%s" % (fmt_num(hp), hp_suffix) if hp else "N/A"
    torque_txt = "%s kgm%s" % (fmt_num(torque), torque_suffix) if torque else "N/A"
    return hp_txt, hp or 0, torque_txt, torque or 0


def parse_energy(text):
    """能量消耗例：'平均 16.3km/ltr 市區 ...' 或 '滿電續航 669km'。回傳 (油耗 km/L 或 None, 純電續航 km 或 None)。"""
    fuel = None
    m = re.search(r"平均\s*(\d+(?:\.\d+)?)\s*km\s*/\s*(?:ltr|l)(?![a-z])", text, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*km\s*/\s*(?:ltr|l)(?![a-z])", text, re.IGNORECASE)
    if m:
        fuel = float(m.group(1))
    rng = None
    m = re.search(r"續航[^\d]{0,6}(\d+(?:\.\d+)?)\s*(?:km|公里)", text, re.IGNORECASE)
    if m:
        rng = float(m.group(1))
    return fuel, rng


def parse_engine(engine_text, is_ev, title):
    """引擎形式例：'渦輪增壓, 直列4缸, DOHC雙凸輪軸, 16氣門'。純電車沒有此欄位。"""
    if is_ev:
        return "純電動馬達"
    parts = [p.strip() for p in engine_text.split(",") if p.strip()]
    induction = next((p for p in parts if re.search(r"進氣|增壓|渦輪", p)), "")
    cylinders = next((p for p in parts if "缸" in p), "")
    result = "/".join(p for p in (induction, cylinders) if p)
    if not result:
        return "N/A"
    if re.search(r"phev|插電", title, re.IGNORECASE):
        result += " (插電式油電)"
    elif re.search(r"hybrid|\bhev\b|油電", title, re.IGNORECASE):
        result += " (油電)"
    return result


def brand_slug_from_trim_url(url):
    seg = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]).lower()
    matches = [slug for slug in BRAND_BY_SLUG if seg.startswith(slug + "-")]
    return max(matches, key=len) if matches else None


def split_title(full_title, slug):
    """標題例：'2026 Land Rover Defender 90 D250'。品牌可能含空格，不能單純用空格切。"""
    year, rest = "", full_title
    head, _, tail = full_title.partition(" ")
    if re.fullmatch(r"20\d{2}", head) and tail:
        year, rest = head, tail
    if slug:
        brand = BRAND_BY_SLUG[slug]
        for cand in sorted({brand, slug, slug.replace("-", " ")}, key=len, reverse=True):
            if rest.lower().startswith(cand.lower() + " "):
                return year, brand, rest[len(cand) + 1:]
        return year, brand, rest
    brand, _, model = rest.partition(" ")
    return year, brand, model or rest


def parse_trim_page(soup, url):
    """解析單一車款規格頁；找不到標題視為失敗（回傳 None），不再產生「未知 / N/A」的垃圾列。"""
    h1 = soup.find("h1")
    full_title = clean_text(h1.get_text()) if h1 else ""
    if not full_title:
        return None
    brand_slug = brand_slug_from_trim_url(url)
    year, brand, model = split_title(full_title, brand_slug)
    price_text, price_val = extract_price(soup)
    specs = read_spec_pairs(soup)

    displacement = specs.get("排氣量", "N/A") or "N/A"
    displacement_val = get_number(displacement)
    power, power_val, torque, torque_val = parse_performance(specs.get("性能數據", ""))
    fuel_val, ev_range = parse_energy(specs.get("能量消耗", ""))
    if ev_range is None and displacement_val == 0:
        ev_range = next((parse_energy(v)[1] for v in specs.values() if "續航" in v), None)

    is_ev = ev_range is not None and displacement_val == 0
    if is_ev:
        fuel, fuel_val = "%s km" % fmt_num(ev_range), ev_range
    elif fuel_val is not None:
        fuel = "%s km/L" % fmt_num(fuel_val)
    elif ev_range is not None:
        fuel, fuel_val = "%s km" % fmt_num(ev_range), ev_range
    else:
        fuel, fuel_val = "N/A", 0

    return {
        "year": year, "brand": brand, "brand_slug": brand_slug or "", "model": model,
        "price": price_text, "price_val": price_val,
        "engine_type": parse_engine(specs.get("引擎形式", ""), is_ev, full_title),
        "displacement": displacement, "displacement_val": displacement_val,
        "transmission": specs.get("變速系統", "N/A") or "N/A",
        "horsepower": power, "horsepower_val": power_val,
        "torque": torque, "torque_val": torque_val,
        "fuel": fuel, "fuel_val": fuel_val, "is_ev": is_ev,
        "url": url,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def extract_brand_models(soup, brand_slug):
    """從品牌頁取出「屬於該品牌」的車系（品牌頁會夾帶別牌車系）→ {車系網址片段: 品牌頁上列出的年份集合}"""
    models = {}
    for a in soup.find_all("a", href=True):
        url = validate_yahoo_url(urljoin(YAHOO_BASE, a["href"]), "/new-cars/model/")
        if not url:
            continue
        raw_seg = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        seg = unquote(raw_seg)
        if not seg.lower().startswith(brand_slug + "-"):
            continue
        m = MODEL_YEAR_RE.match(seg)
        if not m:
            continue
        models.setdefault(raw_seg[:-5], set()).add(int(m.group("year")))
    return models


def plan_model_pages(models, target_years):
    """品牌頁已列出的年份直接使用；較舊、未列出的年份才需要探測。比該車系最新年份更新的年份不可能存在，不探測。"""
    pages = []
    for base, listed in sorted(models.items()):
        newest = max(listed)
        for year in sorted(target_years, reverse=True):
            if year <= newest:
                pages.append({"url": "%s/new-cars/model/%s-%d" % (YAHOO_BASE, base, year), "year": year})
    return pages


# ==========================================
# API
# ==========================================
@app.route("/api/brands")
@auth.login_required
def get_brands():
    return jsonify([{"name": name, "slug": slug} for name, slug in sorted(BRANDS)])


@app.route("/api/brand_models")
@auth.login_required
def brand_models():
    """第 1 步：讀一次品牌頁，回傳要去掃描的「車系+年份」頁面清單。"""
    slug = request.args.get("slug", "")
    if slug not in BRAND_BY_SLUG:
        return jsonify({"error": "unknown brand"}), 400
    target_years = [int(y) for y in re.findall(r"20\d{2}", request.args.get("years", ""))]
    if not target_years:
        target_years = [datetime.now().year]

    url = "%s/new-cars/make/%s" % (YAHOO_BASE, slug)
    try:
        resp = fetch(url)
    except FetchError as e:
        return error_response(url, e)
    if resp.status_code != 200:
        return error_response(url, "HTTP %d" % resp.status_code)
    models = extract_brand_models(BeautifulSoup(resp.text, "html.parser"), slug)
    if not models:
        return error_response(url, "品牌頁找不到任何車系（頁面結構改變或被擋）")
    return jsonify({"pages": plan_model_pages(models, target_years)})


@app.route("/api/model_trims")
@auth.login_required
def model_trims():
    """第 2 步：讀一個「車系+年份」頁，回傳該車系自己的車款（trim）網址；該年份不存在(404)則回傳空清單。"""
    url = validate_yahoo_url(request.args.get("url"), "/new-cars/model/")
    seg = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]) if url else ""
    if not url or not MODEL_YEAR_RE.match(seg):
        return jsonify({"error": "invalid url"}), 400
    try:
        resp = fetch(url)
    except FetchError as e:
        return error_response(url, e)
    if resp.status_code == 404:
        return jsonify({"urls": []})

    prefix = "/new-cars/trim/%s-" % seg.lower()   # 車系頁會夾帶別的車系，必須用「車系+年份」前綴過濾
    urls = []
    for a in BeautifulSoup(resp.text, "html.parser").find_all("a", href=True):
        t_url = validate_yahoo_url(urljoin(YAHOO_BASE, a["href"]), "/new-cars/trim/")
        if not t_url:
            continue
        path = urlparse(t_url).path
        if unquote(path).lower().startswith(prefix) and YAHOO_BASE + path not in urls:
            urls.append(YAHOO_BASE + path)
    return jsonify({"urls": urls})


@app.route("/api/scrape_one")
@auth.login_required
def scrape_one():
    """第 3 步：讀一個車款規格頁。任何失敗都回傳 502，讓前端計入失敗並可重試。"""
    url = validate_yahoo_url(request.args.get("url"), "/new-cars/trim/")
    if not url:
        return jsonify({"error": "invalid url"}), 400
    try:
        resp = fetch(url)
    except FetchError as e:
        return error_response(url, e)
    if resp.status_code != 200:
        return error_response(url, "HTTP %d" % resp.status_code)
    data = parse_trim_page(BeautifulSoup(resp.text, "html.parser"), url)
    if data is None:
        return error_response(url, "找不到車款標題（頁面結構改變或被擋）")
    return jsonify(data)


# ==========================================
# 快取快照：只新增，不覆蓋、不刪除（要清理請直接到 NAS 資料夾手動刪檔）
# ==========================================
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SNAP_DIR = os.path.join(DATA_DIR, "snapshots")
SNAP_SCHEMA = 1
SNAP_ID_RE = re.compile(r"^\d{8}_\d{6}(?:-\d+)?$")
MAX_SNAPSHOT_ROWS = 20000
_snap_lock = threading.Lock()
_meta_cache = {}

_ROW_TEXT_FIELDS = ("year", "brand", "model", "price", "engine_type", "displacement", "transmission",
                    "horsepower", "torque", "fuel", "fetched_at")
_ROW_NUM_FIELDS = ("price_val", "displacement_val", "horsepower_val", "torque_val", "fuel_val")


def sanitize_row(row):
    """只保留已知欄位並檢查型別；網址必須是 Yahoo 車款頁。不合法回傳 None。"""
    if not isinstance(row, dict):
        return None
    url = validate_yahoo_url(row.get("url"), "/new-cars/trim/")
    if not url:
        return None
    slug = row.get("brand_slug")
    clean = {"url": url, "brand_slug": slug if slug in BRAND_BY_SLUG else "", "is_ev": bool(row.get("is_ev"))}
    for key in _ROW_TEXT_FIELDS:
        clean[key] = str(row.get(key) or "")[:200]
    for key in _ROW_NUM_FIELDS:
        v = row.get(key, 0)
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e9
        clean[key] = v if ok else 0
    return clean


def _snap_path(sid):
    return os.path.join(SNAP_DIR, sid + ".json")


def read_snapshot(sid):
    if not SNAP_ID_RE.match(sid or ""):
        raise ValueError("invalid snapshot id")
    with open(_snap_path(sid), "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise ValueError("bad snapshot format")
    return data


def write_snapshot(data):
    """寫成新檔：檔名不存在才寫（同一秒重複會加 -2、-3），先寫暫存檔再改名，不會留下寫到一半的快照。"""
    os.makedirs(SNAP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with _snap_lock:
        sid, n = stamp, 1
        while os.path.exists(_snap_path(sid)):
            n += 1
            sid = "%s-%d" % (stamp, n)
        data["id"] = sid
        tmp = _snap_path(sid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, _snap_path(sid))
    return sid


def list_snapshots():
    if not os.path.isdir(SNAP_DIR):
        return []
    result = []
    for name in os.listdir(SNAP_DIR):
        sid, ext = os.path.splitext(name)
        if ext != ".json" or not SNAP_ID_RE.match(sid):
            continue
        try:
            st = os.stat(_snap_path(sid))
        except OSError:
            continue
        stamp = (st.st_mtime_ns, st.st_size)
        cached = _meta_cache.get(sid)
        if cached and cached[0] == stamp:
            result.append(cached[1])
            continue
        try:
            data = read_snapshot(sid)
        except (OSError, ValueError) as e:
            log.warning("略過無法讀取的快照 %s: %s", name, e)
            continue
        meta = {"id": sid, "created_at": str(data.get("created_at", "")), "rows": len(data["rows"]),
                "combos": len(data.get("coverage") or []), "base": data.get("base"),
                "note": str(data.get("note", ""))[:100], "incomplete": bool(data.get("incomplete")),
                "size": st.st_size}
        _meta_cache[sid] = (stamp, meta)
        result.append(meta)
    return sorted(result, key=lambda m: m["id"], reverse=True)


def _valid_coverage(item):
    if not isinstance(item, dict):
        return None
    brand, year = item.get("brand"), item.get("year")
    if brand not in BRAND_BY_SLUG or isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        return None
    return brand, year


@app.route("/api/snapshots")
@auth.login_required
def snapshots_list():
    return jsonify(list_snapshots())


@app.route("/api/snapshots/<sid>")
@auth.login_required
def snapshots_get(sid):
    if not SNAP_ID_RE.match(sid):
        return jsonify({"error": "invalid snapshot id"}), 400
    try:
        return jsonify(read_snapshot(sid))
    except FileNotFoundError:
        return jsonify({"error": "snapshot not found"}), 404
    except (OSError, ValueError) as e:
        log.error("快照讀取失敗 %s: %s", sid, e)
        return jsonify({"error": "snapshot unreadable"}), 500


@app.route("/api/snapshots", methods=["POST"])
@auth.login_required
def snapshots_create():
    """把「這次新抓到的列＋已完整掃描的品牌年份」合併進基底快照，存成一份新快照。基底快照本身不會被動到。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid json"}), 400

    base_id, base = payload.get("base") or None, None
    if base_id:
        try:
            base = read_snapshot(str(base_id))
        except (OSError, ValueError):
            return jsonify({"error": "base snapshot unreadable"}), 400

    raw_rows = payload.get("rows") or []
    if not isinstance(raw_rows, list) or len(raw_rows) > MAX_SNAPSHOT_ROWS:
        return jsonify({"error": "invalid rows"}), 400
    new_rows = [r for r in map(sanitize_row, raw_rows) if r]
    now = datetime.now().isoformat(timespec="seconds")
    for r in new_rows:
        r["fetched_at"] = r["fetched_at"] or now

    raw_cov = payload.get("coverage") or []
    if not isinstance(raw_cov, list):
        return jsonify({"error": "invalid coverage"}), 400
    new_cov = [c for c in map(_valid_coverage, raw_cov) if c]
    if not new_rows and not new_cov:
        return jsonify({"error": "nothing to save"}), 400

    coverage, merged = {}, {}
    if base:
        for item in base.get("coverage") or []:
            key = _valid_coverage(item)
            if key:
                coverage[key] = str(item.get("scanned_at", ""))
        for r in map(sanitize_row, base["rows"]):
            if r:
                merged[r["url"]] = r
    for key in new_cov:
        coverage[key] = now
    for r in new_rows:
        merged[r["url"]] = r          # 新抓的覆蓋同網址舊資料；沒被重抓到的舊列原樣保留
    if len(merged) > MAX_SNAPSHOT_ROWS:
        return jsonify({"error": "too many rows"}), 400

    snapshot = {
        "schema": SNAP_SCHEMA, "created_at": now, "app_version": VERSION, "base": base_id,
        "note": str(payload.get("note") or "")[:100], "incomplete": bool(payload.get("incomplete")),
        "coverage": [{"brand": b, "year": y, "scanned_at": t} for (b, y), t in sorted(coverage.items())],
        "rows": list(merged.values()),
    }
    try:
        sid = write_snapshot(snapshot)
    except OSError as e:
        log.error("快照寫入失敗: %s", e)
        return jsonify({"error": "cannot write snapshot"}), 500
    log.info("新快照 %s：%d 台、%d 組（新增/更新 %d 台，基底 %s）", sid, len(merged), len(coverage), len(new_rows), base_id)
    return jsonify({"id": sid, "rows": len(merged), "combos": len(coverage),
                    "dropped": len(raw_rows) - len(new_rows)}), 201


@app.route("/")
@auth.login_required
def index():
    return render_template_string(HTML_TEMPLATE, years=get_dynamic_years(), current_year=str(datetime.now().year),
                                  version=VERSION)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    log.info("Yahoo 汽車超級比較器 %s 啟動，監聽 0.0.0.0:%d", VERSION, port)
    try:
        from waitress import serve
    except ImportError:
        # 映像檔沒重建時的保險：功能不受影響，但請盡快重建映像檔以使用 waitress
        log.warning("找不到 waitress，改用 Flask 內建伺服器；請重新建置映像檔 (docker compose build --no-cache)")
        app.run(host="0.0.0.0", port=port, threaded=True)
    else:
        serve(app, host="0.0.0.0", port=port, threads=8)
