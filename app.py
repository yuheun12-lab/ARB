import os
import time
import threading
import requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

CACHE = {"updated_at": "", "items": [], "error": ""}
CACHE_LOCK = threading.Lock()

FOCUS_DEFAULT = ["KAT", "CHIP", "XRP", "TRX", "SOL", "BTC", "ETH"]
REFRESH_SEC = int(os.getenv("REFRESH_SEC", "5"))


def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def get_bithumb_prices():
    r = requests.get("https://api.bithumb.com/public/ticker/ALL_KRW", timeout=7)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "0000":
        raise RuntimeError(f"Bithumb error: {data}")
    result = {}
    for sym, item in data.get("data", {}).items():
        if sym == "date":
            continue
        price = safe_float(item.get("closing_price"))
        if price > 0:
            result[sym.upper()] = price
    return result


def get_upbit_prices():
    markets = requests.get(
        "https://api.upbit.com/v1/market/all",
        params={"isDetails": "false"},
        timeout=7,
    )
    markets.raise_for_status()
    krw_markets = [
        item["market"]
        for item in markets.json()
        if item.get("market", "").startswith("KRW-")
    ]

    result = {}
    for i in range(0, len(krw_markets), 100):
        chunk = krw_markets[i:i + 100]
        tickers = requests.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(chunk)},
            timeout=7,
        )
        tickers.raise_for_status()
        for item in tickers.json():
            sym = item["market"].replace("KRW-", "").upper()
            price = safe_float(item.get("trade_price"))
            if price > 0:
                result[sym] = price
    return result


def build_spreads():
    bithumb = get_bithumb_prices()
    upbit = get_upbit_prices()
    common = sorted(set(bithumb) & set(upbit))
    items = []

    for sym in common:
        bp = bithumb[sym]
        up = upbit[sym]
        if bp <= 0 or up <= 0:
            continue

        cheaper = "빗썸" if bp < up else "업비트"
        pricier = "업비트" if bp < up else "빗썸"
        buy_p = min(bp, up)
        sell_p = max(bp, up)
        diff_pct = (sell_p - buy_p) / buy_p * 100

        items.append({
            "symbol": sym,
            "bithumb": bp,
            "upbit": up,
            "cheaper": cheaper,
            "pricier": pricier,
            "buy_p": buy_p,
            "sell_p": sell_p,
            "diff_pct": diff_pct,
            "direction": f"{cheaper} → {pricier}",
            "focus": sym in FOCUS_DEFAULT,
        })

    items.sort(key=lambda x: x["diff_pct"], reverse=True)
    return items


def updater():
    while True:
        try:
            items = build_spreads()
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            with CACHE_LOCK:
                CACHE["updated_at"] = now
                CACHE["items"] = items
                CACHE["error"] = ""
        except Exception as e:
            with CACHE_LOCK:
                CACHE["error"] = str(e)
        time.sleep(REFRESH_SEC)


@app.route("/api/spreads")
def api_spreads():
    with CACHE_LOCK:
        return jsonify(CACHE)


HTML = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="ARB SCAN">
<meta name="theme-color" content="#07090e">
<title>ARB SCAN Mobile</title>
<style>
:root {
  --bg:#07090e;
  --panel:#0d1018;
  --line:#1d2738;
  --text:#d8e3f0;
  --muted:#718096;
  --green:#00ff88;
  --blue:#00b4d8;
  --yellow:#ffd60a;
  --red:#ff4466;
}
* { box-sizing:border-box; }
body {
  margin:0;
  background:var(--bg);
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  padding: env(safe-area-inset-top) 14px env(safe-area-inset-bottom);
}
header {
  position:sticky;
  top:0;
  z-index:10;
  background:linear-gradient(180deg,var(--bg) 70%,rgba(7,9,14,.75));
  padding:18px 0 12px;
}
.title {
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:10px;
}
h1 {
  margin:0;
  font-size:26px;
  letter-spacing:1px;
  color:var(--green);
}
.ver {
  font-size:11px;
  color:#000;
  background:var(--yellow);
  padding:4px 8px;
  border-radius:999px;
  font-weight:800;
}
.sub {
  margin-top:6px;
  color:var(--muted);
  font-size:12px;
}
.controls {
  display:grid;
  grid-template-columns:1fr 94px;
  gap:8px;
  margin-top:14px;
}
input, button {
  border:1px solid var(--line);
  background:var(--panel);
  color:var(--text);
  border-radius:12px;
  padding:12px;
  font-size:14px;
}
button {
  color:#000;
  background:var(--green);
  font-weight:800;
}
.filters {
  display:flex;
  gap:8px;
  overflow-x:auto;
  padding:10px 0 2px;
}
.pill {
  white-space:nowrap;
  border:1px solid var(--line);
  color:var(--muted);
  border-radius:999px;
  padding:8px 10px;
  font-size:12px;
}
.pill.active {
  color:#000;
  background:var(--blue);
  border-color:var(--blue);
  font-weight:800;
}
.status {
  margin:8px 0 12px;
  font-size:12px;
  color:var(--muted);
}
.error { color:var(--red); }
.card {
  background:var(--panel);
  border:1px solid var(--line);
  border-radius:18px;
  padding:14px;
  margin:10px 0;
  box-shadow:0 10px 30px rgba(0,0,0,.18);
}
.row {
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:12px;
}
.symbol {
  font-size:22px;
  font-weight:900;
  letter-spacing:.5px;
}
.rank {
  color:var(--muted);
  font-size:12px;
}
.diff {
  font-size:22px;
  color:var(--green);
  font-weight:900;
  text-align:right;
}
.dir {
  margin-top:8px;
  font-size:13px;
  color:var(--yellow);
}
.prices {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:12px;
}
.pricebox {
  border:1px solid var(--line);
  border-radius:14px;
  padding:10px;
}
.label {
  color:var(--muted);
  font-size:11px;
  margin-bottom:6px;
}
.price {
  font-size:16px;
  font-weight:800;
}
.cheaper {
  border-color:rgba(0,255,136,.45);
}
.cheaper .label::after {
  content:"  매수";
  color:var(--green);
}
.empty {
  text-align:center;
  color:var(--muted);
  padding:40px 0;
}
.footer {
  color:var(--muted);
  font-size:11px;
  text-align:center;
  padding:18px 0 26px;
}
</style>
</head>
<body>
<header>
  <div class="title">
    <h1>ARB SCAN</h1>
    <div class="ver">MOBILE</div>
  </div>
  <div class="sub">업비트 · 빗썸 KRW 마켓 가격차 순위</div>

  <div class="controls">
    <input id="search" placeholder="코인 검색: KAT, CHIP..." oninput="render()">
    <button onclick="load()">새로고침</button>
  </div>

  <div class="filters">
    <div class="pill active" data-filter="all" onclick="setFilter('all')">전체</div>
    <div class="pill" data-filter="focus" onclick="setFilter('focus')">주요코인</div>
    <div class="pill" data-filter="over1" onclick="setFilter('over1')">1% 이상</div>
    <div class="pill" data-filter="bithumb" onclick="setFilter('bithumb')">빗썸이 쌈</div>
    <div class="pill" data-filter="upbit" onclick="setFilter('upbit')">업비트가 쌈</div>
  </div>
  <div class="status" id="status">불러오는 중...</div>
</header>

<main id="list"></main>
<div class="footer">홈화면에 추가하면 앱처럼 사용할 수 있어요.</div>

<script>
let DATA = [];
let FILTER = 'all';

function fmt(n) {
  n = Number(n || 0);
  if (n >= 1000) return n.toLocaleString('ko-KR', {maximumFractionDigits:0});
  if (n >= 1) return n.toLocaleString('ko-KR', {maximumFractionDigits:2});
  return n.toFixed(8);
}

function setFilter(f) {
  FILTER = f;
  document.querySelectorAll('.pill').forEach(p => p.classList.toggle('active', p.dataset.filter === f));
  render();
}

async function load() {
  const status = document.getElementById('status');
  try {
    status.textContent = '업데이트 중...';
    const res = await fetch('/api/spreads', {cache:'no-store'});
    const json = await res.json();
    DATA = json.items || [];
    status.innerHTML = `업데이트: ${json.updated_at || '-'} · ${DATA.length}개 비교` + (json.error ? ` <span class="error">· ${json.error}</span>` : '');
    render();
  } catch (e) {
    status.innerHTML = `<span class="error">서버 연결 실패: ${e}</span>`;
  }
}

function filtered() {
  const q = document.getElementById('search').value.trim().toUpperCase();
  return DATA.filter(x => {
    if (q && !x.symbol.includes(q)) return false;
    if (FILTER === 'focus' && !x.focus) return false;
    if (FILTER === 'over1' && x.diff_pct < 1) return false;
    if (FILTER === 'bithumb' && x.cheaper !== '빗썸') return false;
    if (FILTER === 'upbit' && x.cheaper !== '업비트') return false;
    return true;
  }).slice(0, 50);
}

function render() {
  const list = document.getElementById('list');
  const rows = filtered();
  if (!rows.length) {
    list.innerHTML = '<div class="empty">조건에 맞는 코인이 없어요.</div>';
    return;
  }

  list.innerHTML = rows.map((x, i) => {
    const bCheap = x.cheaper === '빗썸';
    const uCheap = x.cheaper === '업비트';
    return `
      <section class="card">
        <div class="row">
          <div>
            <div class="rank">#${i + 1}</div>
            <div class="symbol">${x.symbol}</div>
          </div>
          <div>
            <div class="diff">+${Number(x.diff_pct).toFixed(3)}%</div>
            <div class="rank">${x.direction}</div>
          </div>
        </div>
        <div class="dir">싼 곳에서 매수 → 비싼 곳에서 매도</div>
        <div class="prices">
          <div class="pricebox ${bCheap ? 'cheaper' : ''}">
            <div class="label">빗썸</div>
            <div class="price">${fmt(x.bithumb)}원</div>
          </div>
          <div class="pricebox ${uCheap ? 'cheaper' : ''}">
            <div class="label">업비트</div>
            <div class="price">${fmt(x.upbit)}원</div>
          </div>
        </div>
      </section>
    `;
  }).join('');
}

load();
setInterval(load, 5000);
</script>
</body>
</html>
"""


@app.route("/")
def home():
    return Response(HTML, mimetype="text/html; charset=utf-8")


if __name__ == "__main__":
    thread = threading.Thread(target=updater, daemon=True)
    thread.start()
    time.sleep(1)
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
