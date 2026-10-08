"""Password-gated public proxy. Never exposes mock/admin routes.

HTTP is deliberately supported for this synthetic, user-authorised experiment.
The random lab password must not be reused elsewhere. It is NOT TLS protection.
"""
import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fixtures import ROOT
from large_fixture import NAME as LARGE_NAME

CONFIG = json.loads((ROOT / "public-access.json").read_text())
ORIGIN = CONFIG["origin"]
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["64.176.188.89"])
buckets = {}
transfer_limit = asyncio.Semaphore(3)


def rate(key, maximum):
    now = int(time.time() // 60)
    count, epoch = buckets.get(key, (0, now))
    count = count + 1 if epoch == now else 1
    if len(buckets) > 4096:
        buckets.clear()
    buckets[key] = count, now
    return count <= maximum


def signature(value):
    return hmac.new(bytes.fromhex(CONFIG["cookie_key"]), value.encode(), hashlib.sha256).hexdigest()


def session_ok(cookie):
    try:
        expiry, nonce, mac = cookie.split(".")
        within_window = CONFIG["expires"] is None or int(expiry) <= CONFIG["expires"]
        return time.time() < int(expiry) and within_window and hmac.compare_digest(mac, signature(expiry + "." + nonce))
    except (ValueError, AttributeError):
        return False


@app.middleware("http")
async def boundary(request, call_next):
    if CONFIG["expires"] is not None and time.time() >= CONFIG["expires"]:
        return JSONResponse({"detail": "The temporary public test window has expired"}, 410)
    ip = request.client.host
    if not rate((ip, "requests"), 120):
        return JSONResponse({"detail": "Request rate exceeded; retry in one minute"}, 429)
    origin = request.headers.get("origin")
    if origin and origin != ORIGIN:
        return JSONResponse({"detail": "Cross-origin requests denied"}, 403)
    if request.method == "POST" and request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "Cross-site requests denied"}, 403)
    if request.url.path not in {"/login", "/login.css", "/favicon.ico"} and not session_ok(request.cookies.get("lab_session")):
        return RedirectResponse("/login", 303) if request.url.path == "/" else JSONResponse({"detail": "Laboratory login required"}, 401)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # A no-referrer policy can turn a browser form POST's Origin into "null",
    # conflicting with the strict origin check above. Keep same-origin login
    # submissions identifiable without disclosing referrers to other sites.
    response.headers["Referrer-Policy"] = "same-origin" if request.url.path == "/login" else "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
    return response


def login_page(error=""):
    expiry = (datetime.fromtimestamp(CONFIG["expires"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
              if CONFIG["expires"] is not None else "No scheduled expiry — until you ask to close it / 无定时关闭")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in · Data delivery lab</title><link rel="stylesheet" href="/login.css"></head>
<body><header><span class="wordmark">DATA DELIVERY / LAB</span><span class="access">Password-protected public test</span></header>
<main><section class="intro"><p class="eyebrow">PRIVATE EXPERIMENT / PUBLIC ENTRANCE</p>
<h1>A small lab.<br>Ready when you are.</h1><p class="lead">Official DataLink and Product Streamer.<br>Synthetic files. Simulated dependencies.</p></section>
<aside class="boundary"><strong>HTTP · not encrypted / 非加密连接</strong><p>Use only the generated laboratory password. Never enter an SKA password, token or any password you use elsewhere.</p><p>Public access: {expiry}</p></aside>
<section class="workbench"><form method="post" action="/login" class="controls"><h2>Enter the laboratory</h2>
<label for="password">Laboratory access password / 测试访问口令</label><input id="password" name="password" type="password" required maxlength="128" autocomplete="off">
<div class="actions"><button type="submit">Enter lab</button></div><p role="status">{error}</p>
<p class="note">口令保存在你的本地 public-access-credentials.txt 文件中。网站不因登录会话过期而关闭；需要时重新登录即可。</p></form>
<div class="response"><h2>What you can test</h2><p>Resolve a DID and inspect its VOTable.</p><p>Download a file or a three-member TAR.</p><p>Check byte ranges and SHA-256.</p><p>Run checks and export evidence.</p></div></section></main></body></html>'''


@app.get("/login")
async def login():
    return HTMLResponse(login_page())


@app.get("/login.css")
async def css():
    return FileResponse(ROOT / "static/style.css")


@app.get("/favicon.ico")
async def favicon():
    raise HTTPException(404)


async def read_body(request, maximum):
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > maximum:
            raise HTTPException(413, "Request body too large")
    return bytes(body)


@app.post("/login")
async def authenticate(request: Request):
    if not rate((request.client.host, "login"), 8) or not rate(("global", "login"), 40):
        raise HTTPException(429, "Too many login attempts; retry in one minute")
    body = await read_body(request, 4096)
    password = parse_qs(body.decode("utf-8", errors="replace")).get("password", [""])[0]
    digest = await asyncio.to_thread(hashlib.scrypt, password.encode(), salt=bytes.fromhex(CONFIG["salt"]), n=16384, r=8, p=1)
    if not hmac.compare_digest(digest.hex(), CONFIG["password_hash"]):
        return HTMLResponse(login_page("Incorrect laboratory password."), status_code=401)
    session_expiry = int(time.time()) + 12 * 3600
    if CONFIG["expires"] is not None:
        session_expiry = min(session_expiry, CONFIG["expires"])
    session = str(session_expiry) + "." + secrets.token_hex(16)
    response = RedirectResponse("/", 303)
    response.set_cookie("lab_session", session + "." + signature(session), httponly=True, samesite="strict",
                        secure=False, max_age=max(1, session_expiry - int(time.time())))
    return response


GET_PATHS = {"/", "/static/style.css", "/static/app.js", "/static/sha256.js", "/lab/info", "/lab/status",
             "/lab/large/info", "/static/large.js", "/static/download_large.py",
             "/datalink/v1/links", "/datalink/v1/ping", "/datalink/v1/health",
             "/streamer/v1/ping", "/streamer/v1/health"}
POST_PATHS = {"/lab/run", "/streamer/v1/data/product"}


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def forward(path: str, request: Request):
    target = "/" + path
    allowed_report = re.fullmatch(r"/lab/reports/[0-9a-f-]{36}\.json", target)
    allowed_fixture = target in {"/fixtures/lab.test/" + n for n in ("image.fits", "readme.txt", "metadata.json", "range.bin", LARGE_NAME)}
    if request.method == "GET" and target not in GET_PATHS and not allowed_report and not allowed_fixture:
        raise HTTPException(404)
    if request.method == "POST" and target not in POST_PATHS:
        raise HTTPException(404)
    if target == "/lab/run" and not rate(("global", "suite"), 4):
        raise HTTPException(429, "Maximum four test suites per minute")
    if len(request.url.query) > 2048:
        raise HTTPException(414)
    body = await read_body(request, 1024 * 1024)
    await transfer_limit.acquire()
    client = httpx.AsyncClient(timeout=60, trust_env=False)
    try:
        headers = {k: request.headers[k] for k in ("content-type", "authorization", "range", "if-range") if k in request.headers}
        headers['accept-encoding'] = 'identity'
        req = client.build_request(request.method, "http://127.0.0.1:18080" + target,
                                   params=request.query_params, content=body, headers=headers)
        upstream = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        transfer_limit.release()
        raise HTTPException(502, "Private lab service unavailable")
    async def cleanup():
        await upstream.aclose()
        await client.aclose()
        transfer_limit.release()
    keep = {k: v for k, v in upstream.headers.items() if k.lower() in
            {"content-type", "content-length", "content-disposition", "content-range", "accept-ranges", "etag", "last-modified"}}
    return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code,
                             headers=keep, background=BackgroundTask(cleanup))
