"""
CIFR Options Portfolio Monitor - Web Server
============================================
A lightweight Flask server that fetches live CIFR option prices
from Nasdaq and serves a beautiful mobile-friendly dashboard.

Deploy free on Render.com, Railway.app, or Fly.io.
"""

import json
import urllib.request
import re
import os
import time
import threading
from datetime import datetime, date
from flask import Flask, Response, send_from_directory

app = Flask(__name__)
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ── YOUR POSITIONS (edit if you open/close positions) ──────────────────
POSITIONS = [
    {"label": "Nov 20 '26 $13 Call", "strike": "13.00", "strike_num": 13, "expiry": "2026-11-20",
     "contracts": 220, "cost_per": 5.007, "fromdate": "2026-11-20", "todate": "2026-11-20"},
    {"label": "Jun 18 '26 $15 Call", "strike": "15.00", "strike_num": 15, "expiry": "2026-06-18",
     "contracts": 105, "cost_per": 5.054, "fromdate": "2026-06-18", "todate": "2026-06-18"},
    {"label": "Oct 16 '26 $16 Call", "strike": "16.00", "strike_num": 16, "expiry": "2026-10-16",
     "contracts": 134, "cost_per": 6.658, "fromdate": "2026-10-16", "todate": "2026-10-16"},
]
TOTAL_COST_BASIS = 252425
# ───────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Cache to avoid hammering Nasdaq on every request
_cache = {"data": None, "time": 0}
CACHE_TTL = 120  # seconds


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def fetch_stock_price():
    url = "https://www.google.com/finance/quote/CIFR:NASDAQ"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode()
    m = re.search(r'data-last-price="([^"]+)"', html)
    return float(m.group(1)) if m else None


def fetch_option(fromdate, todate, strike):
    url = (
        f"https://api.nasdaq.com/api/quote/CIFR/option-chain"
        f"?assetclass=stocks&limit=100&fromdate={fromdate}&todate={todate}"
        f"&money=all&callput=call"
    )
    data = fetch_json(url)
    rows = data.get("data", {}).get("table", {}).get("rows", [])
    return next((r for r in rows if r.get("strike") == strike), None)


def parse_val(v):
    if v is None or v == "--" or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def days_until(date_str):
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (target - date.today()).days


def gather_data():
    now = time.time()
    if _cache["data"] and (now - _cache["time"]) < CACHE_TTL:
        return _cache["data"]

    stock_price = fetch_stock_price()
    results = []

    for pos in POSITIONS:
        try:
            match = fetch_option(pos["fromdate"], pos["todate"], pos["strike"])
            bid = parse_val(match.get("c_Bid")) if match else None
            ask = parse_val(match.get("c_Ask")) if match else None
            last = parse_val(match.get("c_Last")) if match else None
            vol = match.get("c_Volume", "--") if match else "--"
            oi = match.get("c_Openinterest", "--") if match else "--"
        except Exception:
            bid = ask = last = None
            vol = oi = "--"

        mid = (bid + ask) / 2 if bid and ask else last
        cost_basis = pos["contracts"] * pos["cost_per"] * 100
        value = pos["contracts"] * mid * 100 if mid else None
        pnl = value - cost_basis if value else None
        pnl_pct = pnl / cost_basis if pnl is not None else None
        dte = days_until(pos["expiry"])
        intrinsic = max(0, stock_price - pos["strike_num"]) if stock_price else None
        time_val = max(0, mid - intrinsic) if mid and intrinsic is not None else None

        results.append({
            **pos, "bid": bid, "ask": ask, "last": last, "mid": mid,
            "vol": vol, "oi": oi, "cost_basis": cost_basis, "value": value,
            "pnl": pnl, "pnl_pct": pnl_pct, "dte": dte,
            "intrinsic": intrinsic, "time_val": time_val,
        })

    total_value = sum(r["value"] for r in results if r["value"])
    total_pnl = total_value - TOTAL_COST_BASIS
    total_pnl_pct = total_pnl / TOTAL_COST_BASIS

    d = {
        "stock_price": stock_price,
        "positions": results,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "timestamp": datetime.now().strftime("%b %d, %Y %I:%M:%S %p ET"),
    }

    _cache["data"] = d
    _cache["time"] = now
    return d


def fmt(n):
    return f"${n:,.0f}"

def fmt2(n):
    return f"${n:,.2f}"

def pct(n):
    return f"{'+'if n >= 0 else ''}{n*100:.1f}%"


def build_html(d):
    sp = d["stock_price"]
    tp = d["total_pnl"]
    tpp = d["total_pnl_pct"]
    tv = d["total_value"]
    pnl_color = "#22c55e" if tp >= 0 else "#ef4444"
    pnl_bg = "#0a1f0a" if tp >= 0 else "#1f0a0a"
    pnl_border = "#14532d" if tp >= 0 else "#7f1d1d"
    pnl_sign = "+" if tp >= 0 else ""

    cards = ""
    for p in d["positions"]:
        pc = "#22c55e" if (p["pnl"] or 0) >= 0 else "#ef4444"
        ps = "+" if (p["pnl"] or 0) >= 0 else ""
        dte_bg = "#7f1d1d33" if p["dte"] < 60 else "#78350f33" if p["dte"] < 120 else "#1e293b"
        dte_color = "#fca5a5" if p["dte"] < 60 else "#fbbf24" if p["dte"] < 120 else "#94a3b8"

        cards += f"""
    <div class="card">
      <div class="card-head">
        <div class="card-title">{p['label']}</div>
        <div class="dte" style="background:{dte_bg};color:{dte_color}">{p['dte']}d</div>
      </div>
      <div class="row3">
        <div class="stat"><div class="sl">Contracts</div><div class="sv bright">{p['contracts']}</div></div>
        <div class="stat"><div class="sl">Bid / Ask</div><div class="sv">{fmt2(p['bid']) if p['bid'] else '—'} / {fmt2(p['ask']) if p['ask'] else '—'}</div></div>
        <div class="stat"><div class="sl">Mid</div><div class="sv bright">{fmt2(p['mid']) if p['mid'] else '—'}</div></div>
      </div>
      <div class="row3" style="margin-top:8px">
        <div class="stat"><div class="sl">Intrinsic</div><div class="sv">{fmt2(p['intrinsic']) if p['intrinsic'] is not None else '—'}</div></div>
        <div class="stat"><div class="sl">Time Value</div><div class="sv">{fmt2(p['time_val']) if p['time_val'] is not None else '—'}</div></div>
        <div class="stat"><div class="sl">Position Value</div><div class="sv bright">{fmt(p['value']) if p['value'] else '—'}</div></div>
      </div>
      <div class="pnl-row">
        <div><span class="sl">P&L</span><span style="color:{pc};font-weight:700;font-size:15px;margin-left:8px">{ps}{fmt(p['pnl']) if p['pnl'] is not None else '—'}</span></div>
        <div style="color:{pc};font-weight:700;font-size:15px">{pct(p['pnl_pct']) if p['pnl_pct'] is not None else '—'}</div>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta property="og:title" content="CIFR Portfolio | {pnl_sign}{fmt(tp)} ({pct(tpp)})">
<meta property="og:description" content="CIFR ${sp:.2f} | Portfolio {fmt(tv)} | P&L {pnl_sign}{fmt(tp)}">
<meta property="og:image" content="/profile.jpg">
<meta name="theme-color" content="#0a0e17">
<title>CIFR {pnl_sign}{fmt(tp)}</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0e17;color:#e2e8f0;font-family:'JetBrains Mono','SF Mono','Courier New',monospace;padding:20px;padding-top:max(20px,env(safe-area-inset-top));-webkit-font-smoothing:antialiased;min-height:100dvh}}
.header{{border-bottom:1px solid #1e293b;padding-bottom:16px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}}
.header-left{{flex:1}}
.header-video{{width:130px;height:130px;border-radius:12px;object-fit:cover;border:2px solid #1e293b;margin-left:14px;flex-shrink:0}}
.eyebrow{{font-size:9px;letter-spacing:3px;color:#64748b;text-transform:uppercase;margin-bottom:4px}}
.title{{font-size:22px;font-weight:700;color:#f8fafc}}
.title span{{color:#64748b;font-weight:400;font-size:13px}}
.stock-price{{font-size:32px;font-weight:700;color:#f8fafc;margin-top:8px}}
.ts{{font-size:9px;color:#475569;margin-top:4px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px}}
.scard{{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:14px}}
.scard .sl{{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:2px;margin-bottom:4px}}
.scard .sv{{font-size:20px;font-weight:700;color:#f8fafc}}
.scard .sub{{font-size:12px;margin-top:2px}}
.card{{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-bottom:10px}}
.card-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.card-title{{font-size:13px;font-weight:700;color:#e2e8f0}}
.dte{{font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px}}
.row3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.stat .sl{{font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:1.5px}}
.stat .sv{{font-size:13px;font-weight:600;color:#94a3b8;margin-top:2px}}
.stat .sv.bright{{color:#f8fafc}}
.pnl-row{{display:flex;justify-content:space-between;align-items:center;margin-top:10px;padding-top:10px;border-top:1px solid #1e293b}}
.footer{{font-size:10px;color:#475569;text-align:center;margin-top:16px;line-height:1.5}}
.refresh{{display:block;width:100%;background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:14px;border-radius:8px;font-size:13px;font-family:inherit;cursor:pointer;margin-top:14px;text-align:center;text-decoration:none}}
.refresh:active{{background:#334155}}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="eyebrow">CIFR Options Portfolio</div>
    <div style="font-size:14px;font-weight:600;color:#94a3b8;font-style:italic;margin-bottom:6px">Path to Tony's Billions</div>
    <div class="title">CIFR <span>Cipher Digital</span></div>
    <div class="stock-price">{fmt2(sp) if sp else '—'}</div>
    <div class="ts">{d['timestamp']} · Nasdaq Delayed</div>
  </div>
  <video class="header-video" autoplay loop playsinline muted id="vid">
    <source src="/celebration.mp4" type="video/mp4">
  </video>
</div>

<div class="grid2">
  <div class="scard">
    <div class="sl">Portfolio Value</div>
    <div class="sv">{fmt(tv)}</div>
  </div>
  <div class="scard" style="background:{pnl_bg};border-color:{pnl_border}">
    <div class="sl">Total P&L</div>
    <div class="sv" style="color:{pnl_color}">{pnl_sign}{fmt(tp)}</div>
    <div class="sub" style="color:{pnl_color}">{pct(tpp)} on {fmt(TOTAL_COST_BASIS)} basis</div>
  </div>
</div>

{cards}

<a class="refresh" href="/" onclick="this.textContent='Refreshing...'">⟳ Refresh Quotes</a>

<div class="footer">
  459 contracts · ~$45,900 per $1 move · Data cached {CACHE_TTL}s<br>
  Cost basis: {fmt(TOTAL_COST_BASIS)} · DTE: <span style="color:#fbbf24">yellow &lt;120d</span> · <span style="color:#fca5a5">red &lt;60d</span>
</div>

<button id="sound-btn" onclick="toggleSound()" style="position:fixed;bottom:20px;right:20px;z-index:10;background:rgba(30,41,59,0.9);border:1px solid #334155;color:#94a3b8;width:48px;height:48px;border-radius:50%;font-size:20px;cursor:pointer;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)">🔇</button>

<script>
var v=document.getElementById('vid');
var b=document.getElementById('sound-btn');
function unmuteOnce(){{
  v.muted=false;
  b.textContent='🔊';
  document.removeEventListener('click',unmuteOnce);
  document.removeEventListener('touchstart',unmuteOnce);
}}
document.addEventListener('click',unmuteOnce);
document.addEventListener('touchstart',unmuteOnce);
function toggleSound(){{
  v.muted=!v.muted;
  b.textContent=v.muted?'🔇':'🔊';
}}
</script>
</body>
</html>"""


@app.route("/profile.jpg")
def profile_image():
    return send_from_directory(APP_DIR, "profile.jpg", mimetype="image/jpeg")


@app.route("/celebration.mp4")
def celebration_video():
    return send_from_directory(APP_DIR, "celebration.mp4", mimetype="video/mp4")


@app.route("/")
def index():
    try:
        d = gather_data()
        html = build_html(d)
        return Response(html, mimetype="text/html")
    except Exception as e:
        return Response(
            f"""<html><body style="background:#0a0e17;color:#fca5a5;font-family:monospace;padding:40px">
            <h2>Error fetching data</h2><p>{e}</p>
            <a href="/" style="color:#94a3b8">Try again</a></body></html>""",
            mimetype="text/html",
        )


@app.route("/api")
def api():
    try:
        d = gather_data()
        return json.dumps(d, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
