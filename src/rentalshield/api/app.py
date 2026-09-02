"""
RentalShield API server.

Serves the web UI at / and the REST API at /audit.
Run with:  python scripts/serve.py
"""

from __future__ import annotations

import functools
import io

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response

# Raise Starlette's per-part size limit (default 1 MB) to 10 MB
# so base64-encoded car images and logos don't get rejected.
from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = 10 * 1024 * 1024   # 10 MB

from rentalshield.api.routes import router

app = FastAPI(title="RentalShield", version="0.1.0")
app.include_router(router)


# ── PWA assets ────────────────────────────────────────────────────────────────

# Minimal 1×1 transparent PNG — fallback when PIL is unavailable
_TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


@functools.lru_cache(maxsize=None)
def _make_icon_png(size: int) -> bytes:
    """Render a RentalShield shield icon (red shield + white RS) at the given size."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img  = Image.new("RGBA", (size, size), (15, 17, 23, 255))   # dark bg
        draw = ImageDraw.Draw(img)

        # Shield polygon — centred, pointed at the bottom
        cx  = size / 2
        top = size * 0.10
        bot = size * 0.92
        mid = size * 0.60
        hw  = size * 0.36    # half-width of the shield

        shield = [
            (cx - hw, top),   # top-left
            (cx + hw, top),   # top-right
            (cx + hw, mid),   # right
            (cx,      bot),   # tip
            (cx - hw, mid),   # left
        ]
        draw.polygon([(int(x), int(y)) for x, y in shield], fill=(230, 57, 70, 255))

        # "RS" text centred in the upper body of the shield
        font_size = int(size * 0.30)
        font = None
        for path in (
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.otf",
            "/Library/Fonts/Arial.ttf",
        ):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                pass
        if font is None:
            font = ImageFont.load_default()

        text = "RS"
        bb   = draw.textbbox((0, 0), text, font=font)
        ty_c = (top + mid) / 2          # vertical centre of shield body
        tx   = int(cx - (bb[2] - bb[0]) / 2 - bb[0])
        ty   = int(ty_c - (bb[3] - bb[1]) / 2 - bb[1])
        draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception:
        return _TINY_PNG


_SW_JS = """\
const CACHE = 'rs-v1';
const SHELL = ['/', '/manifest.json', '/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

// Cache-first for UI shell; network-only for API calls
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || e.request.url.includes('/audit')) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
"""


@app.get("/manifest.json")
def pwa_manifest():
    return JSONResponse(
        {
            "name": "RentalShield",
            "short_name": "RentalShield",
            "description": "AI-powered car rental damage documentation",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f1117",
            "theme_color": "#e63946",
            "orientation": "portrait-primary",
            "icons": [
                {"src": "/icon-192.png", "sizes": "192x192",
                 "type": "image/png", "purpose": "any maskable"},
                {"src": "/icon-512.png", "sizes": "512x512",
                 "type": "image/png", "purpose": "any maskable"},
            ],
        },
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
def service_worker():
    return Response(_SW_JS, media_type="application/javascript")


@app.get("/icon-192.png")
def icon_192():
    return Response(_make_icon_png(192), media_type="image/png")


@app.get("/icon-512.png")
def icon_512():
    return Response(_make_icon_png(512), media_type="image/png")


# ── Web UI (single-page, no external dependencies) ────────────────────────────

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RentalShield</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#e63946">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="RentalShield">
<link rel="apple-touch-icon" href="/icon-192.png">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    /* Charcoal + Electric: modern, bold, high contrast */
    --bg:      #1a1a2e;  --surface: #252d4a;  --border:  #3a4563;
    --text:    #F5F7FA;  --muted:   #9CA3AF;  --accent:  #FF6B6B;
    --gold:    #FFD700;  --cyan:    #00D4FF;  --green:   #10B981;  --yellow:  #FBBF24;
    --radius:  12px;     --font:    -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  body { background:var(--bg); color:var(--text); font-family:var(--font);
         min-height:100vh; display:flex; flex-direction:column;
         align-items:center; padding:1.5rem 1rem 4rem; }

  /* ── Header ── */
  header { text-align:center; margin-bottom:1.75rem; }
  header h1 { font-size:1.9rem; font-weight:700; letter-spacing:-.5px;
              background:linear-gradient(135deg, var(--text) 0%, var(--text) 65%, var(--gold) 100%);
              -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
  header h1 span { color:var(--accent); }
  header p { color:var(--muted); margin-top:.35rem; font-size:.9rem; }

  /* ── Card ── */
  .card { background:var(--surface); border:1px solid var(--border);
          box-shadow:0 4px 16px rgba(0,0,0,.3);
          border-radius:var(--radius); padding:1.5rem;
          width:100%; max-width:560px; margin-bottom:1rem; }
  .card-title { font-size:.75rem; font-weight:600; color:var(--muted);
                text-transform:uppercase; letter-spacing:.07em; margin-bottom:1.1rem; }

  /* ── Photo guide ── */
  .guide-toggle { display:flex; align-items:center; justify-content:space-between;
                  cursor:pointer; user-select:none; }
  .guide-toggle svg { transition:transform .25s; flex-shrink:0; }
  .guide-toggle.open svg { transform:rotate(180deg); }
  .guide-body { overflow:hidden; max-height:0; transition:max-height .35s ease; }
  .guide-body.open { max-height:1200px; }

  .phase-label { font-size:.72rem; font-weight:700; text-transform:uppercase;
                 letter-spacing:.09em; margin:1rem 0 .45rem;
                 display:flex; align-items:center; gap:.5rem; }
  .phase-label.p1 { color:var(--blue); }
  .phase-label.p2 { color:var(--accent); }
  .phase-label::after { content:''; flex:1; height:1px; background:currentColor; opacity:.25; }

  .steps { display:grid; gap:.55rem; }
  .step { display:flex; gap:.85rem; align-items:flex-start;
          background:var(--bg); border-radius:8px; padding:.7rem .85rem; }
  .step.highlight { background:rgba(230,57,70,.07); border:1px solid rgba(230,57,70,.2); }
  .step-icon { font-size:1.4rem; line-height:1; flex-shrink:0; margin-top:.05rem; }
  .step-text h3 { font-size:.88rem; font-weight:600; margin-bottom:.2rem; }
  .step-text p  { font-size:.8rem; color:var(--muted); line-height:1.45; }
  .step-text .tip { color:var(--yellow); font-size:.78rem; margin-top:.3rem;
                    font-weight:600; }

  .closeup-alert { margin-top:.85rem; background:rgba(230,57,70,.08);
                   border:1px solid rgba(230,57,70,.25); border-radius:8px;
                   padding:.8rem .95rem; font-size:.82rem; line-height:1.55; }
  .closeup-alert strong { color:var(--accent); display:block; margin-bottom:.3rem;
                          font-size:.85rem; }

  .guide-extra { margin-top:.75rem; background:rgba(74,158,255,.08);
                 border:1px solid rgba(74,158,255,.2); border-radius:8px;
                 padding:.75rem .9rem; font-size:.82rem; color:var(--muted);
                 line-height:1.5; }
  .guide-extra strong { color:var(--blue); }

  /* ── Photo buttons ── */
  .btn-row { display:grid; grid-template-columns:1fr 1fr; gap:.75rem; }
  .btn-cam, .btn-gal { display:flex; align-items:center; justify-content:center;
                       gap:.5rem; padding:.85rem .5rem; border:none; border-radius:var(--radius);
                       font-size:.95rem; font-weight:600; cursor:pointer; transition:all .2s ease; }
  .btn-cam { background:var(--accent); color:#fff; box-shadow:0 4px 12px rgba(255,107,107,.3); }
  .btn-gal { background:var(--border); color:var(--text); border:1px solid var(--cyan); }
  .btn-cam:hover { opacity:.92; box-shadow:0 6px 20px rgba(255,107,107,.45); transform:translateY(-2px); }
  .btn-gal:hover { background:rgba(0,212,255,.1); box-shadow:0 0 12px rgba(0,212,255,.2); }
  .btn-cam:active, .btn-gal:active { opacity:.65; }

  /* ── Thumbnail queue ── */
  #thumb-area { margin-top:1rem; }
  .thumb-header { display:flex; align-items:center; justify-content:space-between;
                  margin-bottom:.6rem; }
  #thumb-count { font-size:.82rem; color:var(--muted); }
  .clear-btn { background:none; border:1px solid var(--border); color:var(--muted);
               border-radius:6px; padding:.2rem .55rem; font-size:.75rem; cursor:pointer; }
  .clear-btn:hover { border-color:var(--accent); color:var(--accent); }
  .thumb-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:.4rem; }
  .thumb-item { position:relative; aspect-ratio:1; border-radius:6px; overflow:hidden;
                background:var(--bg); }
  .thumb-item img { width:100%; height:100%; object-fit:cover; display:block; }
  .thumb-remove { position:absolute; top:2px; right:2px; width:18px; height:18px;
                  border-radius:50%; background:rgba(0,0,0,.7); color:#fff; border:none;
                  font-size:10px; line-height:18px; text-align:center; cursor:pointer;
                  display:flex; align-items:center; justify-content:center; }
  .thumb-remove:hover { background:var(--accent); }

  /* ── Fields ── */
  .fields { display:grid; gap:.7rem; }
  label { font-size:.82rem; color:var(--muted); display:block; margin-bottom:.25rem; }
  input[type=text] { width:100%; background:var(--bg); border:1px solid var(--border);
                     border-radius:6px; color:var(--text); padding:.5rem .75rem;
                     font-size:.92rem; outline:none; transition:border-color .2s; }
  input[type=text]:focus { border-color:var(--accent); }

  /* ── Submit ── */
  button#submit { width:100%; max-width:560px; padding:.85rem;
                  background:linear-gradient(135deg, var(--accent) 0%, #FF5252 100%);
                  color:#fff; border:2px solid var(--gold);
                  border-radius:var(--radius); font-size:1rem; font-weight:600;
                  cursor:pointer; transition:all .25s ease; margin-bottom:1rem;
                  box-shadow:0 6px 20px rgba(255,107,107,.35); position:relative; }
  button#submit:hover   {
    opacity:.95;
    transform:translateY(-2px);
    box-shadow:0 10px 32px rgba(255,107,107,.45), 0 0 20px rgba(0,212,255,.2);
    border-color:var(--cyan);
  }
  button#submit:active  { transform:translateY(0); }
  button#submit:disabled { opacity:.35; cursor:not-allowed; box-shadow:none; }

  /* ── Status ── */
  #status-card { display:none; }
  .status-row { display:flex; align-items:center; gap:.75rem; margin-bottom:.9rem; }
  .spinner { width:20px; height:20px; border:3px solid var(--border);
             border-top-color:var(--cyan); border-radius:50%;
             animation:spin .8s linear infinite; flex-shrink:0;
             box-shadow:inset 0 0 8px rgba(0,212,255,.3); }
  @keyframes spin { to { transform:rotate(360deg); } }
  #progress-msg { font-size:.92rem; }
  .progress-bar-wrap { background:var(--border); border-radius:99px;
                       height:5px; overflow:hidden; margin-bottom:1.1rem;
                       box-shadow:inset 0 0 4px rgba(0,0,0,.3); }
  .progress-bar { height:100%; background:linear-gradient(90deg, var(--cyan) 0%, var(--accent) 100%);
                  border-radius:99px; width:0%; transition:width .4s ease;
                  box-shadow:0 0 8px rgba(0,212,255,.6); }

  /* ── Company branding ── */
  .company-row { display:flex; align-items:center; gap:.65rem;
                 margin-bottom:.9rem; padding-bottom:.9rem;
                 border-bottom:1px solid var(--border); }
  .company-logo { width:36px; height:36px; object-fit:contain;
                  border-radius:6px; background:#fff; padding:3px; flex-shrink:0; }
  .company-badge { display:inline-flex; align-items:center; justify-content:center;
                   width:36px; height:36px; border-radius:6px;
                   background:var(--accent); color:#fff;
                   font-weight:700; font-size:.85rem; flex-shrink:0; }
  .company-name { font-weight:600; font-size:.95rem; }
  .company-sub  { font-size:.75rem; color:var(--muted); }

  /* ── Result ── */
  .damage-badge { font-size:1.05rem; font-weight:600; margin-bottom:.6rem; }
  .coverage-title { font-size:.78rem; color:var(--muted); text-transform:uppercase;
                    letter-spacing:.06em; margin:.8rem 0 .4rem; }
  .cov-grid { display:grid; grid-template-columns:1fr 1fr; gap:.4rem; }
  .cov-item { font-size:.83rem; padding:.35rem .5rem; border-radius:6px; }
  .cov-item.ok      { background:rgba(46,194,126,.12); color:var(--green); }
  .cov-item.missing { background:rgba(245,166,35,.1);  color:var(--yellow); }

  /* ── Damage list ── */
  .dmg-list { margin-top:.9rem; display:flex; flex-direction:column; gap:.35rem; }
  .dmg-row { display:flex; align-items:flex-start; gap:.55rem; font-size:.82rem;
             padding:.4rem .55rem; border-radius:6px; background:var(--bg); }
  .dmg-photo { font-size:.7rem; color:var(--muted); flex-shrink:0; min-width:3rem; padding-top:.1rem; }
  .dmg-type  { font-weight:700; flex-shrink:0; font-size:.78rem;
               padding:.1rem .4rem; border-radius:4px; text-transform:uppercase;
               letter-spacing:.04em; }
  .dmg-type.SCRATCH { background:rgba(74,158,255,.18); color:var(--blue); }
  .dmg-type.SCUFF   { background:rgba(245,166,35,.18); color:var(--yellow); }
  .dmg-type.DENT    { background:rgba(230,57,70,.18);  color:var(--accent); }
  .dmg-type.CHIP,.dmg-type.CRACK,.dmg-type.RUST,.dmg-type.MISSING,.dmg-type.OTHER
                    { background:rgba(122,127,153,.18); color:var(--muted); }
  .dmg-loc  { color:var(--text); line-height:1.35; }

  .dl-grid { display:grid; grid-template-columns:1fr 1fr; gap:.75rem; margin-top:1.1rem; }
  .dl-btn { display:block; text-align:center; padding:.75rem; border-radius:var(--radius);
            font-weight:600; font-size:.88rem; text-decoration:none; transition:opacity .2s; }
  .dl-btn:hover { opacity:.82; }
  .dl-btn.pdf { background:var(--accent); color:#fff; }
  .dl-btn.zip { background:var(--green);  color:#fff; }
  .error-box { background:rgba(230,57,70,.12); border:1px solid var(--accent);
               border-radius:var(--radius); padding:.9rem; color:var(--accent); font-size:.88rem; }

  /* ── Car photo upload ── */
  .car-photo-row { display:flex; align-items:center; gap:.6rem; margin-top:.4rem; }
  .car-photo-btn { flex-shrink:0; background:var(--border); border:none; color:var(--text);
                   border-radius:6px; padding:.45rem .75rem; font-size:.82rem; cursor:pointer; }
  .car-photo-btn:hover { opacity:.8; }
  #car-photo-name { font-size:.78rem; color:var(--muted); }

  @media (max-width:380px) { .cov-grid, .dl-grid { grid-template-columns:1fr; } }

  /* ── Compare section ── */
  .compare-section { margin-top:1.4rem; border-top:1px solid var(--border); padding-top:1.1rem; }
  .compare-title { font-size:.82rem; font-weight:700; text-transform:uppercase;
                   letter-spacing:.06em; color:var(--muted); margin-bottom:.75rem; }
  .compare-upload { display:flex; gap:.6rem; align-items:center; }
  .compare-file-btn { flex-shrink:0; background:var(--border); border:none; color:var(--text);
                      border-radius:6px; padding:.55rem .9rem; font-size:.82rem; cursor:pointer; }
  .compare-file-btn:hover { opacity:.8; }
  #compare-file-name { font-size:.78rem; color:var(--muted); flex:1; }
  .compare-run-btn { background:var(--blue); color:#fff; border:none; border-radius:6px;
                     padding:.55rem 1rem; font-size:.84rem; font-weight:600; cursor:pointer; }
  .compare-run-btn:disabled { opacity:.45; cursor:default; }
  .compare-run-btn:not(:disabled):hover { opacity:.85; }
  .compare-spinner { font-size:.82rem; color:var(--muted); margin-top:.5rem; }

  .cmp-results { margin-top:1rem; display:flex; flex-direction:column; gap:1rem; }
  .cmp-card { border-radius:var(--radius); padding:.9rem 1rem; }
  .cmp-card.matched   { background:rgba(45,197,120,.1);  border:1px solid rgba(45,197,120,.3); }
  .cmp-card.risk      { background:rgba(230,57,70,.08);  border:1px solid rgba(230,57,70,.3); }
  .cmp-card.extra     { background:rgba(90,147,255,.09); border:1px solid rgba(90,147,255,.3); }
  .cmp-card.uncertain { background:rgba(122,127,153,.09);border:1px solid rgba(122,127,153,.25);}
  .cmp-card-hd { font-weight:700; font-size:.88rem; margin-bottom:.55rem; }
  .cmp-card.matched   .cmp-card-hd { color:var(--green); }
  .cmp-card.risk      .cmp-card-hd { color:var(--accent); }
  .cmp-card.extra     .cmp-card-hd { color:var(--blue); }
  .cmp-card.uncertain .cmp-card-hd { color:var(--muted); }
  .cmp-item { font-size:.8rem; color:var(--text); padding:.25rem 0;
              border-bottom:1px solid rgba(127,127,127,.1); line-height:1.4; }
  .cmp-item:last-child { border-bottom:none; }
  .cmp-item-loc { font-weight:600; }
  .cmp-item-reason { color:var(--muted); font-size:.74rem; }
  .cmp-summary { display:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:.75rem; }
  .cmp-badge { font-size:.78rem; font-weight:600; padding:.25rem .6rem;
               border-radius:20px; white-space:nowrap; }
  .cmp-badge.matched { background:rgba(45,197,120,.18); color:var(--green); }
  .cmp-badge.risk    { background:rgba(230,57,70,.18);  color:var(--accent); }
  .cmp-badge.extra   { background:rgba(90,147,255,.18); color:var(--blue); }

  /* ── Install banners ── */
  #install-banner, #ios-hint {
    display:none; width:100%; max-width:560px;
    background:rgba(74,158,255,.1); border:1px solid rgba(74,158,255,.2);
    border-radius:var(--radius); padding:.7rem 1rem; margin-bottom:.75rem;
    align-items:center; gap:.75rem; font-size:.86rem; }
  #install-banner span, #ios-hint span { flex:1; }
  #install-btn { background:var(--blue); color:#fff; border:none;
    border-radius:6px; padding:.35rem .8rem; font-size:.82rem;
    font-weight:600; cursor:pointer; white-space:nowrap; flex-shrink:0; }
  #install-btn:hover { opacity:.85; }
</style>
</head>
<body>

<header>
  <h1>Rental<span>Shield</span></h1>
  <p id="subtitle">AI-powered car damage documentation</p>
  <div style="margin-top:.75rem; display:flex; gap:.5rem; justify-content:center; flex-wrap:wrap;">
    <button onclick="setLang('en')" style="padding:.3rem .6rem; font-size:.8rem; border:1px solid var(--border); background:transparent; color:var(--text); border-radius:4px; cursor:pointer;" id="lang-en">🇬🇧 English</button>
    <button onclick="setLang('es')" style="padding:.3rem .6rem; font-size:.8rem; border:1px solid var(--border); background:transparent; color:var(--text); border-radius:4px; cursor:pointer;" id="lang-es">🇪🇸 Español</button>
    <button onclick="setLang('it')" style="padding:.3rem .6rem; font-size:.8rem; border:1px solid var(--border); background:transparent; color:var(--text); border-radius:4px; cursor:pointer;" id="lang-it">🇮🇹 Italiano</button>
  </div>
</header>

<!-- ── Install banners ───────────────────────────────────────────────── -->
<div id="install-banner">
  <span>📲 Add RentalShield to your home screen</span>
  <button id="install-btn">Install</button>
</div>
<div id="ios-hint">
  <span>📲 Tap <b>Share ↑</b> then <b>Add to Home Screen</b> to install</span>
</div>

<!-- ── Photo guide (collapsed by default) ──────────────────────────── -->
<div class="card">
  <div class="guide-toggle" id="guide-toggle">
    <span class="card-title" style="margin:0" data-i18n="how-to">📸 How to photograph the car (10–12 photos)</span>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="var(--muted)" stroke-width="2.5" stroke-linecap="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  </div>

  <div class="guide-body" id="guide-body">

    <div class="phase-label p1">Phase 1 — Full-car overview (4 photos)</div>
    <div class="steps">
      <div class="step">
        <div class="step-icon">1️⃣</div>
        <div class="step-text">
          <h3>Front view</h3>
          <p>Stand ~2 m away. Full front bumper, hood, headlights, windshield top.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-icon">2️⃣</div>
        <div class="step-text">
          <h3>Rear view</h3>
          <p>Stand ~2 m behind. Full rear bumper, tail lights, licence plate, roof edge.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-icon">3️⃣</div>
        <div class="step-text">
          <h3>Left side (driver)</h3>
          <p>Stand ~3 m left. Full length from front wheel to rear wheel, roof visible.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-icon">4️⃣</div>
        <div class="step-text">
          <h3>Right side (passenger)</h3>
          <p>Stand ~3 m right. Full length from front wheel to rear wheel, roof visible.</p>
        </div>
      </div>
    </div>

    <div class="phase-label p2">Phase 2 — Wheels & roof (4 photos) ⭐ CRITICAL</div>
    <div class="closeup-alert">
      <strong>🛞 Wheels & 🏠 Roof are top damage areas</strong>
      Kerb rash on rims and roof scratches are the most common charges. Get close-ups of all 4 wheels and the full roof edge from front to back.
    </div>
    <div class="steps" style="margin-top:.65rem">
      <div class="step highlight">
        <div class="step-icon">5️⃣</div>
        <div class="step-text">
          <h3>Front wheels (both)</h3>
          <p>Get ~50 cm away. Photograph the outer rim edge of both front wheels. Check for kerb scuffs.</p>
        </div>
      </div>
      <div class="step highlight">
        <div class="step-icon">6️⃣</div>
        <div class="step-text">
          <h3>Rear wheels (both)</h3>
          <p>Same angle: ~50 cm away, focus on rim edges. This is where damage hides.</p>
        </div>
      </div>
      <div class="step highlight">
        <div class="step-icon">7️⃣</div>
        <div class="step-text">
          <h3>Roof (front to back)</h3>
          <p>Stand 1 m to the side. Photograph the entire roof length from windshield to rear window. Include roof edges.</p>
        </div>
      </div>
      <div class="step highlight">
        <div class="step-icon">8️⃣</div>
        <div class="step-text">
          <h3>Roof rear edge</h3>
          <p>Shoot from behind the car looking up. Capture the rear roof trim and tail light area.</p>
        </div>
      </div>
    </div>

    <div class="phase-label p3">Phase 3 — Close-ups (2–4 photos)</div>
    <div class="steps">
      <div class="step">
        <div class="step-icon">🔍</div>
        <div class="step-text">
          <h3>Front bumper — full width</h3>
          <p>Get 30–50 cm away. Photograph lower bumper and plastic trim in 1–2 shots.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-icon">🔍</div>
        <div class="step-text">
          <h3>Rear bumper — full width</h3>
          <p>Same: 30–50 cm, cover reflectors and corner areas.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-icon">📌</div>
        <div class="step-text">
          <h3>Any visible damage</h3>
          <p>Dents, cracks, trim damage — one close-up per area.</p>
        </div>
      </div>
    </div>

    <div class="guide-extra">
      <strong>Tips:</strong><br>
      · Outdoors in daylight — shadows hide scratches<br>
      · Hold steady — blurry photos are skipped<br>
      · Photograph at <strong>rental pickup</strong>, before driving. Photos are timestamped for disputes.<br>
      · Target: 10–12 photos total. More is better than fewer.
    </div>
  </div>
</div>

<!-- ── Notes/Message (optional) ──────────────────────────────────────────── -->
<div class="card">
  <div class="guide-toggle" id="notes-toggle" style="cursor:pointer;">
    <span class="card-title" style="margin:0">📝 Add a note (optional)</span>
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="var(--muted)" stroke-width="2.5" stroke-linecap="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  </div>

  <div class="guide-body" id="notes-body" style="max-height:0; overflow:hidden; transition:max-height .3s ease;">
    <textarea id="message"
              placeholder="Add any notes or messages (e.g., pre-existing damage, customer contact info, etc.)"
              style="width:100%; min-height:100px; background:var(--bg); border:1px solid var(--border);
                     color:var(--text); padding:.75rem; border-radius:6px; font-family:var(--font);
                     font-size:.9rem; resize:vertical; outline:none;"
              maxlength="500"></textarea>
    <div style="font-size:.75rem; color:var(--muted); margin-top:.35rem;">
      <span id="char-count">0</span>/500 characters
    </div>
  </div>
</div>

<!-- ── Upload ──────────────────────────────────────────────────────────── -->
<div class="card">
  <div class="card-title" data-i18n="add-photos">Add photos</div>

  <!-- Hidden file inputs -->
  <input type="file" id="input-camera"  accept="image/*" capture="environment" style="display:none">
  <input type="file" id="input-gallery" accept=".jpg,.jpeg,.png,.heic,.webp" multiple style="display:none">

  <!-- Two action buttons -->
  <div class="btn-row">
    <button class="btn-cam" id="btn-camera">📷 Take photo</button>
    <button class="btn-gal" id="btn-gallery">🖼 From gallery</button>
  </div>

  <!-- Offline-store restore banner (shown after page reload if there are pending photos) -->
  <div id="offline-restore-banner"
       style="display:none;margin:.75rem 0 0;padding:.6rem .8rem;border-radius:8px;
              background:rgba(45,140,110,.14);color:#a8f0c9;font-size:.85rem;
              border:1px solid rgba(45,140,110,.35);"></div>

  <!-- Thumbnail queue (shown once photos are added) -->
  <div id="thumb-area" style="display:none">
    <div class="thumb-header">
      <span id="thumb-count"></span>
      <button class="clear-btn" id="clear-all">Clear all</button>
    </div>
    <div class="thumb-grid" id="thumb-grid"></div>
  </div>
</div>

<!-- ── Metadata ────────────────────────────────────────────────────────── -->
<div class="card">
  <div class="card-title" data-i18n="rental-details">Rental details (optional)</div>
  <div class="fields">
    <div>
      <label data-i18n="licence-plate">Licence plate</label>
      <input type="text" id="plate" placeholder="e.g. HC 397WW" autocomplete="off" data-placeholder-i18n="plate-example">
    </div>
    <div>
      <label data-i18n="company">Rental company</label>
      <input type="text" id="company" placeholder="e.g. Hertz, Sixt" data-placeholder-i18n="company-example">
    </div>
    <div>
      <label data-i18n="car-model">Car model</label>
      <input type="text" id="car" placeholder="e.g. MG3 Hybrid" data-placeholder-i18n="car-example">
    </div>
    <div>
      <label><span data-i18n="car-photo">Car photo (optional — appears in PDF)</span></label>
      <div class="car-photo-row">
        <button class="car-photo-btn" id="car-photo-btn" data-i18n="select-photo">📷 Select photo</button>
        <span id="car-photo-name" data-i18n="none-selected">none selected</span>
        <input type="file" id="car-photo-input" accept="image/*" style="display:none">
      </div>
    </div>
  </div>
</div>

<button id="submit" disabled>Scan for damage</button>

<!-- ── Status / result ─────────────────────────────────────────────────── -->
<div class="card" id="status-card">
  <div class="card-title">Analysis</div>
  <div class="status-row" id="status-row">
    <div class="spinner" id="spinner"></div>
    <span id="progress-msg">Starting …</span>
  </div>
  <div class="progress-bar-wrap">
    <div class="progress-bar" id="progress-bar"></div>
  </div>
  <div id="result"    style="display:none"></div>
  <div id="error-box" style="display:none" class="error-box"></div>
</div>

<script>
// ── Guide toggle ────────────────────────────────────────────────────────
const guideToggle = document.getElementById('guide-toggle');
const guideBody   = document.getElementById('guide-body');
guideToggle.addEventListener('click', () => {
  const open = guideBody.classList.toggle('open');
  guideToggle.classList.toggle('open', open);
});

// ── Photo queue ─────────────────────────────────────────────────────────
const inputCamera  = document.getElementById('input-camera');
const inputGallery = document.getElementById('input-gallery');
const btnCamera    = document.getElementById('btn-camera');
const btnGallery   = document.getElementById('btn-gallery');
const thumbArea    = document.getElementById('thumb-area');
const thumbGrid    = document.getElementById('thumb-grid');
const thumbCount   = document.getElementById('thumb-count');
const clearAllBtn  = document.getElementById('clear-all');
const submitBtn    = document.getElementById('submit');

// ── Manual car photo upload ──────────────────────────────────────────────
let manualCarPhotoB64 = '';
const carPhotoBtn   = document.getElementById('car-photo-btn');
const carPhotoInput = document.getElementById('car-photo-input');
const carPhotoName  = document.getElementById('car-photo-name');
carPhotoBtn.addEventListener('click', () => carPhotoInput.click());
carPhotoInput.addEventListener('change', async () => {
  const file = carPhotoInput.files[0];
  if (!file) return;
  carPhotoName.textContent = '⏳ Resizing…';
  const blob = file.slice(0, file.size, file.type);
  const b64  = await resizeImageBlob(blob, 400, 250, 0.80);
  if (b64) {
    manualCarPhotoB64 = b64;
    carPhotoName.textContent = '✅ ' + file.name;
  } else {
    carPhotoName.textContent = '⚠ Could not read image';
  }
});

let selectedFiles = [];   // accumulates across multiple camera/gallery sessions

// ── Offline photo store (IndexedDB) ────────────────────────────────────
// Every photo the user selects is saved to the phone's local IndexedDB
// BEFORE any upload attempt. If the network drops mid-upload — or the tab
// gets closed on shaky Wi-Fi — the photos survive and are restored on the
// next page load. Only cleared when the scan actually starts on the server.
const IDB_NAME = 'rentalshield-offline';
const IDB_STORE = 'photos';

// ── Multi-language support (EN, ES, IT) ──────────────────────────────────
const i18n = {
  en: {
    'app-title': 'RentalShield',
    'app-subtitle': 'AI-powered car damage documentation',
    'how-to': 'How to photograph the car (10–12 photos)',
    'add-photos': 'Add photos',
    'take-photo': '📷 Take photo',
    'from-gallery': '🖼 From gallery',
    'scan-button': 'Scan for damage',
    'uploading': 'Uploading photos …',
    'analyzing': 'Analysing …',
    'complete': 'Complete!',
    'offline-queued': '✓ Scan queued. Photos saved on this phone.',
    'offline-retrying': '🔄 Connection restored! Scanning queued photos…',
    'upload-interrupted': '⚠ Upload interrupted. Connection lost.',
    'upload-error': 'Upload failed. Your photos are saved on this phone.',
    'network-error': 'Could not reach the server. Your photos are saved on this phone — try again when you have Wi-Fi or mobile data.',
    'rental-details': 'Rental details (optional)',
    'licence-plate': 'Licence plate',
    'plate-example': 'e.g. HC 397WW',
    'company': 'Rental company',
    'company-example': 'e.g. Hertz, Sixt',
    'car-model': 'Car model',
    'car-example': 'e.g. MG3 Hybrid',
    'car-photo': 'Car photo (optional — appears in PDF)',
    'select-photo': 'Select photo',
    'none-selected': 'none selected',
  },
  es: {
    'app-title': 'RentalShield',
    'app-subtitle': 'Documentación de daños de automóviles impulsada por IA',
    'how-to': 'Cómo fotografiar el automóvil (10–12 fotos)',
    'add-photos': 'Agregar fotos',
    'take-photo': '📷 Tomar foto',
    'from-gallery': '🖼 De la galería',
    'scan-button': 'Escanear daños',
    'uploading': 'Cargando fotos …',
    'analyzing': 'Analizando …',
    'complete': '¡Completo!',
    'offline-queued': '✓ Escaneo en cola. Fotos guardadas en tu teléfono.',
    'offline-retrying': '🔄 ¡Conexión restaurada! Escaneando fotos pendientes…',
    'upload-interrupted': '⚠ Carga interrumpida. Conexión perdida.',
    'upload-error': 'Falló la carga. Tus fotos se guardaron en tu teléfono.',
    'network-error': 'No se puede alcanzar el servidor. Tus fotos se guardaron en tu teléfono — intenta de nuevo cuando tengas Wi-Fi o datos móviles.',
    'rental-details': 'Detalles del alquiler (opcional)',
    'licence-plate': 'Placa de matrícula',
    'plate-example': 'p. ej. HC 397WW',
    'company': 'Compañía de alquiler',
    'company-example': 'p. ej. Hertz, Sixt',
    'car-model': 'Modelo de coche',
    'car-example': 'p. ej. MG3 Hybrid',
    'car-photo': 'Foto del coche (opcional — aparece en PDF)',
    'select-photo': 'Seleccionar foto',
    'none-selected': 'ninguno seleccionado',
  },
  it: {
    'app-title': 'RentalShield',
    'app-subtitle': 'Documentazione dei danni auto con IA',
    'how-to': 'Come fotografare l\'auto (10–12 foto)',
    'add-photos': 'Aggiungi foto',
    'take-photo': '📷 Scatta foto',
    'from-gallery': '🖼 Dalla galleria',
    'scan-button': 'Scansiona danni',
    'uploading': 'Caricamento foto …',
    'analyzing': 'Analisi …',
    'complete': 'Completato!',
    'offline-queued': '✓ Scansione in coda. Foto salvate sul tuo telefono.',
    'offline-retrying': '🔄 Connessione ripristinata! Scansione foto in sospeso…',
    'upload-interrupted': '⚠ Caricamento interrotto. Connessione persa.',
    'upload-error': 'Caricamento fallito. Le tue foto sono salvate sul telefono.',
    'network-error': 'Impossibile raggiungere il server. Le tue foto sono salvate sul telefono — riprova quando hai Wi-Fi o dati mobili.',
    'rental-details': 'Dettagli noleggio (facoltativo)',
    'licence-plate': 'Targa',
    'plate-example': 'es. HC 397WW',
    'company': 'Società di noleggio',
    'company-example': 'es. Hertz, Sixt',
    'car-model': 'Modello auto',
    'car-example': 'es. MG3 Hybrid',
    'car-photo': 'Foto auto (facoltativa — appare nel PDF)',
    'select-photo': 'Seleziona foto',
    'none-selected': 'nessuno selezionato',
  }
};

let currentLang = localStorage.getItem('rentalshield-lang') || 'en';
function t(key) { return i18n[currentLang]?.[key] || i18n.en[key] || key; }

function _translateDOM() {
  // Translate all elements with data-i18n attribute
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });

  // Translate placeholders with data-placeholder-i18n
  document.querySelectorAll('[data-placeholder-i18n]').forEach(el => {
    const key = el.getAttribute('data-placeholder-i18n');
    el.placeholder = t(key);
  });
}

function setLang(lang) {
  currentLang = lang;
  localStorage.setItem('rentalshield-lang', lang);
  _translateDOM();
  updateUIText();
  // Highlight selected language button
  document.querySelectorAll('[id^="lang-"]').forEach(btn => btn.style.opacity = '1');
  document.getElementById('lang-' + lang).style.opacity = '.6';
}

function _idbOpen() {
  return new Promise((resolve, reject) => {
    try {
      const req = indexedDB.open(IDB_NAME, 2);  // version 2 for queue store
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) {
          db.createObjectStore(IDB_STORE, { keyPath: 'key' });
        }
        if (!db.objectStoreNames.contains(IDB_QUEUE_STORE)) {
          db.createObjectStore(IDB_QUEUE_STORE, { keyPath: 'id' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    } catch(e) { reject(e); }
  });
}
async function _idbAdd(file) {
  try {
    const db = await _idbOpen();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).put({
        key: file.name + '|' + file.size,
        name: file.name,
        type: file.type || 'image/jpeg',
        blob: file,
      });
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    db.close();
  } catch(e) { console.warn('IDB add failed:', e); }
}
async function _idbDel(name, size) {
  try {
    const db = await _idbOpen();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).delete(name + '|' + size);
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    db.close();
  } catch(e) { console.warn('IDB del failed:', e); }
}
async function _idbAll() {
  try {
    const db = await _idbOpen();
    const rows = await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readonly');
      const req = tx.objectStore(IDB_STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror   = () => reject(req.error);
    });
    db.close();
    return rows;
  } catch(e) { console.warn('IDB read failed:', e); return []; }
}
async function _idbClear() {
  try {
    const db = await _idbOpen();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).clear();
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    db.close();
  } catch(e) { console.warn('IDB clear failed:', e); }
}

// ── Offline Queue Storage (for pending scans) ────────────────────────────
// Scans that fail due to offline are stored and retried when online.
const IDB_QUEUE_STORE = 'pending_scans';
async function _queueAdd(scanData) {
  try {
    const db = await _idbOpen();
    // Create queue store if it doesn't exist
    if (!db.objectStoreNames.contains(IDB_QUEUE_STORE)) {
      db.close();
      return; // Will be created on next open
    }
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_QUEUE_STORE, 'readwrite');
      tx.objectStore(IDB_QUEUE_STORE).put({
        id: scanData.id || Date.now().toString(),
        timestamp: Date.now(),
        company: scanData.company,
        car: scanData.car,
        plate: scanData.plate,
        logoB64: scanData.logoB64,
        carImgB64: scanData.carImgB64,
        fileNames: scanData.fileNames,
      });
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    db.close();
  } catch(e) { console.warn('Queue add failed:', e); }
}
async function _queueGetAll() {
  try {
    const db = await _idbOpen();
    if (!db.objectStoreNames.contains(IDB_QUEUE_STORE)) {
      db.close();
      return [];
    }
    const rows = await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_QUEUE_STORE, 'readonly');
      const req = tx.objectStore(IDB_QUEUE_STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror   = () => reject(req.error);
    });
    db.close();
    return rows;
  } catch(e) { console.warn('Queue read failed:', e); return []; }
}
async function _queueDel(id) {
  try {
    const db = await _idbOpen();
    if (!db.objectStoreNames.contains(IDB_QUEUE_STORE)) {
      db.close();
      return;
    }
    await new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_QUEUE_STORE, 'readwrite');
      tx.objectStore(IDB_QUEUE_STORE).delete(id);
      tx.oncomplete = resolve;
      tx.onerror    = () => reject(tx.error);
    });
    db.close();
  } catch(e) { console.warn('Queue del failed:', e); }
}

// Restore any photos left from a previous crashed / offline session.
async function _restorePendingPhotos() {
  const rows = await _idbAll();
  if (!rows.length) return;
  rows.forEach(r => {
    try {
      const f = new File([r.blob], r.name, { type: r.type });
      const dup = selectedFiles.some(x => x.name === f.name && x.size === f.size);
      if (!dup) selectedFiles.push(f);
    } catch(e) { console.warn('Restore skipped one photo:', e); }
  });
  renderThumbs();
  const banner = document.getElementById('offline-restore-banner');
  if (banner) {
    banner.textContent = `✓ Restored ${rows.length} photo${rows.length > 1 ? 's' : ''} from your last session. Ready to upload when you have internet.`;
    banner.style.display = 'block';
  }
}
// Kick off restoration on load (non-blocking).
window.addEventListener('DOMContentLoaded', _restorePendingPhotos);

// Update button text and translate DOM based on language
function updateUIText() {
  try {
    document.getElementById('subtitle').textContent = t('app-subtitle');
    btnCamera.textContent = t('take-photo');
    btnGallery.textContent = t('from-gallery');
    submitBtn.textContent = t('scan-button');
    if (currentLang !== 'en') {
      _translateDOM();
    }
    document.querySelectorAll('[id^="lang-"]').forEach(btn => btn.style.opacity = '1');
    document.getElementById('lang-' + currentLang).style.opacity = '.6';
  } catch(e) { console.warn('updateUIText error:', e); }
}

// Wait for DOM to be ready before translating
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', updateUIText);
} else {
  updateUIText();
}

// ── Notes toggle + character counter ────────────────────────────────────
const notesToggle = document.getElementById('notes-toggle');
const notesBody = document.getElementById('notes-body');
const messageInput = document.getElementById('message');
const charCount = document.getElementById('char-count');

notesToggle.addEventListener('click', () => {
  notesToggle.classList.toggle('open');
  if (notesBody.style.maxHeight === '0px' || !notesBody.style.maxHeight) {
    notesBody.style.maxHeight = '250px';
  } else {
    notesBody.style.maxHeight = '0px';
  }
});

messageInput.addEventListener('input', () => {
  charCount.textContent = messageInput.value.length;
});

btnCamera.addEventListener('click',  () => inputCamera.click());
btnGallery.addEventListener('click', () => inputGallery.click());

inputCamera.addEventListener('change', () => addFiles(Array.from(inputCamera.files)));
inputGallery.addEventListener('change', () => addFiles(Array.from(inputGallery.files)));

function addFiles(files) {
  const allowed = /\.(jpe?g|png|heic|webp)$/i;
  files.filter(f => allowed.test(f.name)).forEach(f => {
    // Avoid exact duplicates (same name + size)
    const dup = selectedFiles.some(x => x.name === f.name && x.size === f.size);
    if (!dup) {
      selectedFiles.push(f);
      _idbAdd(f);   // persist to phone immediately — survives network drop
    }
  });
  renderThumbs();
  // Reset inputs so selecting the same file again fires change
  inputCamera.value  = '';
  inputGallery.value = '';
}

function renderThumbs() {
  thumbGrid.innerHTML = '';
  selectedFiles.forEach((f, i) => {
    const url  = URL.createObjectURL(f);
    const item = document.createElement('div');
    item.className = 'thumb-item';
    item.innerHTML = `<img src="${url}" loading="lazy">
      <button class="thumb-remove" data-i="${i}" title="Remove">✕</button>`;
    thumbGrid.appendChild(item);
  });
  thumbGrid.querySelectorAll('.thumb-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const removed = selectedFiles.splice(+btn.dataset.i, 1)[0];
      if (removed) _idbDel(removed.name, removed.size);   // also drop from offline store
      renderThumbs();
    });
  });
  const n = selectedFiles.length;
  thumbCount.textContent = n ? `${n} photo${n > 1 ? 's' : ''} queued` : '';
  thumbArea.style.display = n ? 'block' : 'none';
  submitBtn.disabled = !n;
}

// ── Mobile detection: camera button only makes sense on phone/tablet ────
const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
              || ('ontouchstart' in window && navigator.maxTouchPoints > 1);
if (!isMobile) {
  btnCamera.style.display = 'none';
  btnGallery.style.gridColumn = '1 / -1';  // full width
  btnGallery.textContent = '📂 Select photos';
}

clearAllBtn.addEventListener('click', () => {
  selectedFiles = [];
  _idbClear();
  const banner = document.getElementById('offline-restore-banner');
  if (banner) banner.style.display = 'none';
  renderThumbs();
});

// ── Company logo lookup ──────────────────────────────────────────────────
const COMPANY_DOMAINS = {
  'noleggiare':   'noleggiare.it',
  'hertz':        'hertz.com',
  'sixt':         'sixt.com',
  'europcar':     'europcar.com',
  'avis':         'avis.com',
  'budget':       'budget.com',
  'enterprise':   'enterprise.com',
  'national':     'nationalcar.com',
  'alamo':        'alamo.com',
  'dollar':       'dollar.com',
  'thrifty':      'thrifty.com',
  'goldcar':      'goldcar.es',
  'ok mobility':  'okmobility.com',
  'localiza':     'localiza.com',
  'firefly':      'fireflycarrental.com',
  'interrent':    'interrent.com',
  'record':       'recordrentacar.com',
  'maggiore':     'maggiore.it',
  'autoeuropa':   'autoeuropa.com',
  'leasys':       'leasysrent.com',
};

// Strip common suffixes/qualifiers that don't belong in a logo domain lookup.
// e.g. "Hertz 24/7" → "Hertz", "Sixt Rent a Car" → "Sixt"
function _normaliseCompany(company) {
  return company
    .replace(/\b(24\/7|24-7|rent\s*a\s*car|car\s*rental|mobility|auto|group)\b/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function getLogoUrl(company) {
  const key = _normaliseCompany(company).toLowerCase();
  const domain = COMPANY_DOMAINS[key]
    || Object.entries(COMPANY_DOMAINS).find(([k]) => key.includes(k))?.[1]
    || (key.replace(/\s+/g, '') + '.com');
  return `https://logo.clearbit.com/${domain}`;
}

let submittedCompany = '';

function resizeImageBlob(blob, maxW, maxH, quality) {
  return new Promise(resolve => {
    const img = new Image();
    const url = URL.createObjectURL(blob);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(maxW / img.width, maxH / img.height, 1);
      const w = Math.round(img.width  * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL('image/jpeg', quality).split(',')[1]);
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(''); };
    img.src = url;
  });
}

const CAR_KEYWORDS = [
  'car','automobile','vehicle','motor','suv','hatchback','sedan',
  'crossover','mpv','coupe','saloon','estate','pickup','van',
  'subcompact','compact','supermini','microcar','city car','minivan',
  'mg motor','mg 3','honda','toyota','volkswagen','renault','fiat','ford',
  'hyundai','kia','nissan','peugeot','citroën','opel','skoda','saic',
  'produced by','manufactured by','made by',
];

// Keywords that indicate the image is a building/HQ, not the car itself
const BUILDING_KEYWORDS = [
  'headquarters','building','factory','plant','facility','museum',
  'showroom','dealership','office','entrance','exterior view','facade',
  'logo','badge','emblem','sign','brand',
];

function isCarPage(data) {
  const text = [data.description, data.extract, data.title].join(' ').toLowerCase();
  return CAR_KEYWORDS.some(kw => text.includes(kw));
}

function isLikelyCarImage(data) {
  // Reject if the image description / page description strongly suggests a building
  const desc = (data.description || '').toLowerCase();
  if (BUILDING_KEYWORDS.some(kw => desc.includes(kw))) return false;
  // Require the page to be about a specific car model, not just the brand/company.
  // Brand-only pages (e.g. "Fiat") have thumbnails of HQs; model pages have car photos.
  const title = (data.title || '').toLowerCase();
  const words = title.split(/\s+/);
  // A model page usually has ≥ 2 words (e.g. "Fiat Panda", "Volkswagen Golf")
  if (words.length < 2) {
    console.warn(`Car image: page title "${data.title}" looks like a brand-only page — skipping`);
    return false;
  }
  return true;
}

async function fetchCarImageBase64(carModel) {
  if (!carModel) return '';
  const base = carModel.trim();
  // Build search terms from most-specific to least, always try "car" qualifier first
  const spaced = base.replace(/([a-zA-Z])(\d)/g, '$1 $2').replace(/(\d)([a-zA-Z])/g, '$1 $2');
  const brand   = base.split(/[\s\-_]/)[0];
  const terms = [
    spaced + ' car',
    base + ' car',
    base + ' automobile',
    spaced,
    base,
  ].filter((v, i, a) => v && a.indexOf(v) === i);  // removed brand-only fallback

  for (const term of terms) {
    try {
      const url = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`;
      const resp = await fetch(url, {signal: AbortSignal.timeout(6000), headers: {'Accept': 'application/json'}});
      if (!resp.ok) continue;
      const data = await resp.json();
      // Skip if the Wikipedia page is clearly NOT about a specific car model
      if (!isCarPage(data)) {
        console.log(`Wikipedia "${term}" → "${data.title}" — not a car page, skipping`);
        continue;
      }
      if (!isLikelyCarImage(data)) {
        console.warn(`Wikipedia "${term}" → "${data.title}" — looks like brand/HQ page, skipping`);
        continue;
      }
      console.log(`Wikipedia car page found: "${data.title}" for term "${term}"`);
      const imgUrl = data?.originalimage?.source || data?.thumbnail?.source;
      if (!imgUrl) { console.log('No image on car page'); continue; }
      const imgResp = await fetch(imgUrl, {signal: AbortSignal.timeout(8000)});
      if (!imgResp.ok) continue;
      const blob = await imgResp.blob();
      if (!blob.type.startsWith('image/')) continue;
      const b64 = await resizeImageBlob(blob, 400, 250, 0.80);
      if (b64) { console.log(`Car image fetched OK (${b64.length} chars b64)`); return b64; }
    } catch(e) { console.warn(`Car image fetch error for "${term}":`, e); }
  }
  console.warn('Car image: no Wikipedia result found for', base);
  return '';
}

async function fetchLogoBase64(company) {
  if (!company) return '';
  const key = _normaliseCompany(company).toLowerCase();
  const domain = COMPANY_DOMAINS[key]
    || Object.entries(COMPANY_DOMAINS).find(([k]) => key.includes(k))?.[1]
    || (key.replace(/\s+/g, '') + '.com');
  const sources = [
    `https://logo.clearbit.com/${domain}`,
    `https://www.google.com/s2/favicons?domain=${domain}&sz=128`,
  ];
  for (const src of sources) {
    try {
      const resp = await fetch(src);
      if (!resp.ok) continue;
      const blob = await resp.blob();
      if (!blob.type.startsWith('image/')) continue;
      return await new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]); // base64 only
        reader.readAsDataURL(blob);
      });
    } catch(e) { /* try next */ }
  }
  return '';
}

// ── Submit ──────────────────────────────────────────────────────────────
submitBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) return;
  submittedCompany = document.getElementById('company').value.trim();
  submitBtn.disabled = true;
  document.querySelectorAll('.card').forEach(c => {
    if (c.id !== 'status-card') { c.style.opacity='.45'; c.style.pointerEvents='none'; }
  });

  document.getElementById('status-card').style.display = 'block';
  const carModel = document.getElementById('car').value.trim();
  const plate = document.getElementById('plate').value.trim();

  // Check connection before proceeding
  if (!navigator.onLine) {
    setProgress(2, '📱 No internet connection detected.');
    await new Promise(r => setTimeout(r, 800));

    // Queue the scan for later
    await _queueAdd({
      id: 'scan_' + Date.now(),
      company: submittedCompany,
      car: carModel,
      plate: plate,
      logoB64: manualCarPhotoB64 || '',
      carImgB64: '',
      fileNames: selectedFiles.map(f => f.name),
    });

    setProgress(3, t('offline-queued'));
    await new Promise(r => setTimeout(r, 1000));
    const autoAnalyzeMsg = currentLang === 'es' ? 'Se analizará automáticamente cuando tengas conexión.' :
                           currentLang === 'it' ? 'Verrà analizzato automaticamente quando connesso.' :
                           'Will analyze automatically when connected to Wi-Fi or mobile data.';
    setProgress(5, autoAnalyzeMsg);

    // Disable scan/clear UI after 2s
    await new Promise(r => setTimeout(r, 2000));
    submitBtn.disabled = false;
    document.querySelectorAll('.card').forEach(c => {
      if (c.id !== 'status-card') { c.style.opacity='1'; c.style.pointerEvents='auto'; }
    });
    document.getElementById('status-card').style.display = 'none';
    return;
  }

  // If the user manually uploaded a car photo, use it — no Wikipedia needed
  let carImgB64 = manualCarPhotoB64;
  let logoB64   = '';
  if (!carImgB64) {
    setProgress(3, 'Fetching company logo & car image from internet …');
    [logoB64, carImgB64] = await Promise.all([
      fetchLogoBase64(submittedCompany),
      fetchCarImageBase64(carModel),
    ]);
    if (carModel && !carImgB64) {
      setProgress(4, `⚠ Car image not found for "${carModel}" — upload one manually next time. Continuing …`);
      await new Promise(r => setTimeout(r, 1500));
    }
  } else {
    setProgress(3, 'Fetching company logo …');
    logoB64 = await fetchLogoBase64(submittedCompany);
  }

  const form = new FormData();
  selectedFiles.forEach(f => form.append('files', f));
  form.append('plate',        plate);
  form.append('company',      submittedCompany);
  form.append('car',          carModel);
  form.append('logo_b64',     logoB64);
  form.append('car_img_b64',  carImgB64);
  form.append('message',      messageInput.value || '');

  setProgress(5, t('uploading'));

  let jobId;
  try {
    // Wrap fetch with timeout (30 seconds max) to prevent hanging
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    const r = await fetch('/audit', {
      method:'POST',
      body:form,
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!r.ok) throw new Error(await r.text());
    jobId = (await r.json()).job_id;
  } catch(e) {
    // Check if this is a network/timeout error
    const isNetworkError = /networkerror|failed to fetch|typeerror|aborted/i.test(e.message);

    if (isNetworkError) {
      // Network error during upload → queue the scan for retry
      setProgress(6, '⚠ Upload interrupted. Connection lost.');
      await new Promise(r => setTimeout(r, 800));

      await _queueAdd({
        id: 'scan_' + Date.now(),
        company: submittedCompany,
        car: carModel,
        plate: plate,
        logoB64: manualCarPhotoB64 || '',
        carImgB64: '',
        fileNames: selectedFiles.map(f => f.name),
      });

      const savedMsg = currentLang === 'es' ? '✓ Escaneo guardado. Se reintentará automáticamente cuando tengas conexión.' :
                       currentLang === 'it' ? '✓ Scansione salvata. Verrà riprovata automaticamente quando connesso.' :
                       '✓ Scan saved to phone. Will retry automatically when online.';
      setProgress(7, savedMsg);
      await new Promise(r => setTimeout(r, 2000));

      submitBtn.disabled = false;
      document.querySelectorAll('.card').forEach(c => {
        if (c.id !== 'status-card') { c.style.opacity='1'; c.style.pointerEvents='auto'; }
      });
      document.getElementById('status-card').style.display = 'none';

      showError('Upload interrupted. Scan queued. Will retry when you have Wi-Fi or mobile data.');
      return;
    }

    const msg = 'Upload failed: ' + e.message + ' — your photos are still saved on this phone, tap Scan again to retry.';
    showError(msg);
    return;
  }

  // Server accepted the upload — the photos are safe on the server now.
  // Clear the offline store so we don't restore them again on next visit.
  _idbClear();

  const analysisMsg = currentLang === 'es' ? 'Fotos recibidas — iniciando análisis …' :
                      currentLang === 'it' ? 'Foto ricevute — avvio analisi …' :
                      'Photos received — starting AI analysis …';
  setProgress(15, analysisMsg);
  poll(jobId, 15, 0);
});

// ── Online/Offline Detection + Queue Processing ──────────────────────────
window.addEventListener('online', async () => {
  console.log('Connection restored!');
  const queue = await _queueGetAll();
  if (queue.length === 0) return;

  // Show banner
  const banner = document.getElementById('status-card');
  if (banner) {
    banner.style.display = 'block';
    const msg = document.getElementById('progress-msg');
    if (msg) msg.textContent = `🔄 Connection restored! ${queue.length} scan(s) queued. Processing…`;
  }

  // Process first scan in queue
  const scan = queue[0];
  console.log('Processing queued scan:', scan.id);

  const form = new FormData();

  // Re-fetch the photo blobs from offline store
  const photos = await _idbAll();
  const scanPhotos = photos.filter(p =>
    scan.fileNames && scan.fileNames.includes(p.name)
  );
  scanPhotos.forEach(p => form.append('files', p.blob, p.name));

  form.append('plate',       scan.plate);
  form.append('company',     scan.company);
  form.append('car',         scan.car);
  form.append('logo_b64',    scan.logoB64);
  form.append('car_img_b64', scan.carImgB64);

  try {
    const r = await fetch('/audit', { method:'POST', body:form });
    if (!r.ok) throw new Error(await r.text());
    const { job_id } = await r.json();

    // Remove from queue
    await _queueDel(scan.id);

    // Poll for results
    setProgress(15, 'Analyzing…');
    poll(job_id, 15, 0);
  } catch(e) {
    console.error('Queue processing failed:', e);
    const msg = document.getElementById('progress-msg');
    if (msg) msg.textContent = `⚠ Scan failed: ${e.message}. Will retry when you tap "Scan"`;
  }
});

window.addEventListener('offline', () => {
  console.log('Connection lost!');
});

// ── Polling ─────────────────────────────────────────────────────────────
// consecutiveFailures: transient blips (up to 3 in a row) are swallowed
// silently — the scan keeps polling. Only a persistent outage surfaces
// as an error message. Prevents "Connection error" flashes on shaky Wi-Fi.
function poll(jobId, pct, consecutiveFailures) {
  setTimeout(async () => {
    try {
      const data = await (await fetch(`/audit/${jobId}`)).json();
      if (data.status === 'done') {
        setProgress(100, 'Complete!');
        showResult(data);
      } else if (data.status === 'error') {
        showError(data.error || 'Analysis failed. Please try again.');
      } else {
        pct = Math.min(pct + 5, 88);
        setProgress(pct, data.progress || 'Analysing …');
        poll(jobId, pct, 0);   // reset failure counter after a success
      }
    } catch(e) {
      const fails = (consecutiveFailures || 0) + 1;
      if (fails < 4) {
        // Transient — keep trying, don't scare the user.
        poll(jobId, pct, fails);
      } else {
        showError('Lost connection to the server. Your photos are safe — please refresh and check the job later.');
      }
    }
  }, 3000);
}

// ── UI helpers ───────────────────────────────────────────────────────────
function setProgress(pct, msg) {
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('progress-msg').textContent = msg;
}

const VIEW_LABELS = {
  front:      'Front',
  rear:       'Rear',
  left_side:  'Left side',
  right_side: 'Right side',
  roof:       'Roof',
  wheels:     'Wheels',
};
const REQUIRED = ['front','rear','left_side','right_side'];

function buildCompanyHtml(company) {
  if (!company) return '';
  const initials = company.replace(/[^a-zA-Z0-9 ]/g, '').trim()
    .split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  const key = _normaliseCompany(company).toLowerCase();
  const domain = COMPANY_DOMAINS[key]
    || Object.entries(COMPANY_DOMAINS).find(([k]) => key.includes(k))?.[1]
    || (key.replace(/\s+/g, '') + '.com');
  // Fallback chain: Clearbit → Google favicon → initials badge
  const sources = [
    `https://logo.clearbit.com/${domain}`,
    `https://www.google.com/s2/favicons?domain=${domain}&sz=128`,
  ];
  return `<div class="company-row">
    <img class="company-logo" id="co-logo"
         src="${sources[0]}"
         data-srcs='${JSON.stringify(sources)}'
         data-src-idx="0"
         onerror="
           const srcs = JSON.parse(this.dataset.srcs);
           const next = +this.dataset.srcIdx + 1;
           if (next < srcs.length) {
             this.dataset.srcIdx = next;
             this.src = srcs[next];
           } else {
             this.style.display='none';
             document.getElementById('co-init').style.display='inline-flex';
           }"
         alt="${company}">
    <span class="company-badge" id="co-init" style="display:none">${initials}</span>
    <div>
      <div class="company-name">${company}</div>
      <div class="company-sub">Rental company</div>
    </div>
  </div>`;
}

function showResult(data) {
  document.getElementById('spinner').style.display = 'none';
  const dmg   = data.damages || 0;
  const views = data.covered_views || [];
  const list  = data.damage_list || [];

  let covHtml = '<div class="coverage-title">Photo coverage</div><div class="cov-grid">';
  REQUIRED.forEach(v => {
    const ok = views.includes(v);
    covHtml += `<div class="cov-item ${ok?'ok':'missing'}">
      ${ok ? '✅' : '⚠️'} ${VIEW_LABELS[v]}${ok ? '' : ' — missing'}
    </div>`;
  });
  covHtml += '</div>';

  let dmgListHtml = '';
  if (list.length) {
    dmgListHtml = '<div class="coverage-title">Damages found</div><div class="dmg-list">';
    list.forEach(d => {
      dmgListHtml += `<div class="dmg-row">
        <span class="dmg-photo">📷 ${d.photo}</span>
        <span class="dmg-type ${d.type}">${d.type}</span>
        <span class="dmg-loc">${d.location}</span>
      </div>`;
    });
    dmgListHtml += '</div>';
  }

  document.getElementById('result').innerHTML = `
    ${buildCompanyHtml(submittedCompany)}
    <div class="damage-badge" style="color:${dmg?'var(--yellow)':'var(--green)'}">
      ${dmg ? '⚠ ' + dmg + ' damage(s) found' : '✓ No damage detected'}
    </div>
    ${covHtml}
    ${dmgListHtml}
    <div class="dl-grid">
      <a class="dl-btn pdf" href="${data.report_url}" target="_blank">📄 Report PDF</a>
      <a class="dl-btn zip" href="${data.evidence_url}">🗜 Evidence ZIP</a>
    </div>
    <div class="compare-section">
      <div class="compare-title">🔍 Compare with company contract</div>
      <div class="compare-upload">
        <button class="compare-file-btn" onclick="document.getElementById('cmp-file-input').click()">
          📄 Choose PDF
        </button>
        <span id="compare-file-name">No file selected</span>
        <button class="compare-run-btn" id="cmp-run-btn" disabled
                onclick="runCompare('${data.report_url.split('/')[2]}')">
          Compare
        </button>
      </div>
      <input type="file" id="cmp-file-input" accept=".pdf" style="display:none"
             onchange="onCmpFileChange(this)">
      <div id="compare-spinner" class="compare-spinner" style="display:none">
        ⏳ Analysing company contract … (10–30 s)
      </div>
      <div id="cmp-results"></div>
    </div>`;
  document.getElementById('result').style.display = 'block';
}

function onCmpFileChange(input) {
  const file = input.files[0];
  document.getElementById('compare-file-name').textContent = file ? file.name : 'No file selected';
  document.getElementById('cmp-run-btn').disabled = !file;
}

async function runCompare(jobId) {
  const input = document.getElementById('cmp-file-input');
  const file  = input.files[0];
  if (!file) return;

  document.getElementById('cmp-run-btn').disabled = true;
  document.getElementById('compare-spinner').style.display = 'block';
  document.getElementById('cmp-results').innerHTML = '';

  try {
    const fd = new FormData();
    fd.append('company_pdf', file, file.name);
    const resp = await fetch('/audit/' + jobId + '/compare', { method: 'POST', body: fd });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({detail: resp.statusText}));
      throw new Error(err.detail || resp.statusText);
    }
    const data = await resp.json();
    showCompareResults(data);
  } catch (e) {
    document.getElementById('cmp-results').innerHTML =
      '<div class="error-box">⚠ Compare failed: ' + e.message + '</div>';
  } finally {
    document.getElementById('compare-spinner').style.display = 'none';
    document.getElementById('cmp-run-btn').disabled = false;
  }
}

function showCompareResults(data) {
  const matched = data.matched || [];
  const risk    = data.risk    || [];
  const extra   = data.extra_protection || [];
  const uncert  = data.uncertain || [];

  let html = '<div class="cmp-summary">';
  html += `<span class="cmp-badge matched">✅ ${matched.length} matched</span>`;
  html += `<span class="cmp-badge risk">🔴 ${risk.length} risk</span>`;
  html += `<span class="cmp-badge extra">🛡 ${extra.length} extra protection</span>`;
  if (uncert.length) html += `<span class="cmp-badge" style="background:rgba(127,127,127,.15);color:var(--muted)">❓ ${uncert.length} uncertain</span>`;
  html += '</div><div class="cmp-results">';

  if (risk.length) {
    html += '<div class="cmp-card risk"><div class="cmp-card-hd">🔴 Risk — Company listed, your scan missed</div>';
    risk.forEach(r => {
      html += `<div class="cmp-item">
        <span class="cmp-item-loc">${r.type} — ${r.location}</span>
        ${r.notes ? '<br><span class="cmp-item-reason">' + r.notes + '</span>' : ''}
        ${r.reason ? '<br><span class="cmp-item-reason">→ ' + r.reason + '</span>' : ''}
      </div>`;
    });
    html += '</div>';
  }

  if (extra.length) {
    html += '<div class="cmp-card extra"><div class="cmp-card-hd">🛡 Extra protection — You found it, company did not list</div>';
    extra.forEach(r => {
      html += `<div class="cmp-item">
        <span class="cmp-item-loc">${r.type} — ${r.location}</span>
        ${r.reason ? '<br><span class="cmp-item-reason">→ ' + r.reason + '</span>' : ''}
      </div>`;
    });
    html += '</div>';
  }

  if (matched.length) {
    html += '<div class="cmp-card matched"><div class="cmp-card-hd">✅ Matched — Protected on both sides</div>';
    matched.forEach(r => {
      html += `<div class="cmp-item">
        <span class="cmp-item-loc">${r.type} — ${r.location}</span>
        ${r.reason ? '<br><span class="cmp-item-reason">→ ' + r.reason + '</span>' : ''}
      </div>`;
    });
    html += '</div>';
  }

  if (uncert.length) {
    html += '<div class="cmp-card uncertain"><div class="cmp-card-hd">❓ Uncertain — Manual review needed</div>';
    uncert.forEach(r => {
      html += `<div class="cmp-item">
        <span class="cmp-item-loc">${r.type} — ${r.location}</span>
        ${r.reason ? '<br><span class="cmp-item-reason">→ ' + r.reason + '</span>' : ''}
      </div>`;
    });
    html += '</div>';
  }

  html += '</div>';
  document.getElementById('cmp-results').innerHTML = html;
}

function showError(msg) {
  document.getElementById('spinner').style.display = 'none';
  setProgress(100, 'Error');
  document.getElementById('error-box').textContent = '⚠ ' + msg;
  document.getElementById('error-box').style.display = 'block';
}

// ── PWA ──────────────────────────────────────────────────────────────────
let _deferredInstall = null;

// Android / Chrome: intercept the browser's native install prompt
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  _deferredInstall = e;
  document.getElementById('install-banner').style.display = 'flex';
});

document.getElementById('install-btn').addEventListener('click', async () => {
  if (!_deferredInstall) return;
  _deferredInstall.prompt();
  await _deferredInstall.userChoice;
  _deferredInstall = null;
  document.getElementById('install-banner').style.display = 'none';
});

// iOS Safari: show Share → Add to Home Screen hint when not already installed
const _isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent);
const _isInstalled = window.navigator.standalone === true
  || window.matchMedia('(display-mode: standalone)').matches;
if (_isIOS && !_isInstalled) {
  document.getElementById('ios-hint').style.display = 'flex';
}

// Register service worker (enables offline shell + installability)
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_HTML)
