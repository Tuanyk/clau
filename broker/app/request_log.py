"""Per-request structured log + read-only dashboard.

Every request through the broker is appended as a single JSONL line to
`/var/log/broker/requests.log` (overridable via BROKER_LOG_FILE). The
`/dashboard` route renders the last N entries as a self-refreshing HTML
page so the user can audit broker activity without trusting it as a black box.

By default the log is metadata-only. If BROKER_LOG_BODIES=1 is set, request
bodies are truncated at MAX_BODY_BYTES and known sensitive fields are redacted.
Binary payloads are recorded as a size-only placeholder.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from secrets import compare_digest

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

LOG_FILE = Path(os.environ.get("BROKER_LOG_FILE", "/var/log/broker/requests.log"))
MAX_BODY_BYTES = 4 * 1024
DASHBOARD_LIMIT = 200
LOG_BODIES = os.environ.get("BROKER_LOG_BODIES") == "1"
SENSITIVE_KEY_RE = re.compile(
    r"(authorization|access[_-]?token|refresh[_-]?token|api[_-]?key|secret|password)",
    re.IGNORECASE,
)
BINARY_PREFIXES = (
    "image/", "video/", "audio/", "application/octet-stream",
    # Multipart envelopes carry binary payloads (image uploads). The text
    # fields inside aren't worth the noise of displaying the raw envelope
    # with replacement chars — path + size is enough context.
    "multipart/form-data",
)

log = logging.getLogger("broker")


def _make_logger() -> logging.Logger:
    """Dedicated JSONL logger; rotates at 50 MB, keeps 3 generations."""
    req_log = logging.getLogger("broker.requests")
    req_log.propagate = False
    req_log.setLevel(logging.INFO)
    if req_log.handlers:
        return req_log
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE, maxBytes=50 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        req_log.addHandler(handler)
    except OSError as exc:
        log.warning("request log disabled — cannot write %s: %s", LOG_FILE, exc)
    return req_log


_req_log = _make_logger()


def _redact_json(value):
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY_RE.search(str(key)) else _redact_json(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def _redact_text(text: str) -> str:
    return re.sub(
        r"(?i)(authorization:\s*bearer\s+|access_token[=\":\s]+|refresh_token[=\":\s]+|client_secret[=\":\s]+|api[_-]?key[=\":\s]+)[^&\s\",}]+",
        r"\1<redacted>",
        text,
    )


def _content_length(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def _summarize(body: bytes, content_type: str) -> str:
    ct = (content_type or "").lower()
    if any(ct.startswith(p) for p in BINARY_PREFIXES):
        return f"<{ct or 'binary'} {len(body)} bytes>"
    if len(body) > MAX_BODY_BYTES:
        head = body[:MAX_BODY_BYTES].decode("utf-8", "replace")
        return f"{_redact_text(head)}\n…<truncated, total {len(body)} bytes>"
    text = body.decode("utf-8", "replace")
    if ct.startswith("application/json"):
        try:
            return json.dumps(_redact_json(json.loads(text)), ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return _redact_text(text)


def _auth_failure(request: Request) -> JSONResponse | None:
    token = os.environ.get("BROKER_AUTH_TOKEN")
    if not token:
        return JSONResponse({"detail": "broker auth token missing"}, status_code=503)

    auth = request.headers.get("authorization", "")
    scheme, _, supplied = auth.partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(supplied, token):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    return None


async def request_log_middleware(request: Request, call_next):
    """Authenticates requests and logs metadata. Request bodies are opt-in."""
    start = time.perf_counter()
    req_body = b""
    response = _auth_failure(request)
    if response is None and LOG_BODIES:
        req_body = await request.body()

        async def receive():
            return {"type": "http.request", "body": req_body, "more_body": False}

        request._receive = receive

    if response is None:
        response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query) or None,
        "status": response.status_code,
        "ms": round(elapsed_ms),
        "req_size": len(req_body) if LOG_BODIES else _content_length(request.headers.get("content-length")),
        "resp_size": _content_length(response.headers.get("content-length")),
        "req_ct": request.headers.get("content-type", ""),
        "resp_ct": response.headers.get("content-type", ""),
    }
    if LOG_BODIES:
        entry["req_body"] = _summarize(req_body, request.headers.get("content-type", ""))

    _req_log.info(json.dumps(entry, ensure_ascii=False))
    log.info(
        "%s %s -> %d (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _read_recent_entries(limit: int = DASHBOARD_LIMIT) -> list[dict]:
    if not LOG_FILE.exists():
        return []
    # 1 MB tail is enough for ~200 entries even with maxed-out 4 KB bodies.
    try:
        with LOG_FILE.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 1_048_576))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    for line in tail.splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


_DASHBOARD_CSS = """
* { box-sizing: border-box; }
body { font: 12px/1.45 ui-monospace, Menlo, Consolas, monospace;
       background:#0d1117; color:#e6edf3; margin:0; padding:1rem 1.25rem; }
header { display:flex; align-items:baseline; gap:1rem; margin:0 0 .75rem; }
header h1 { font-size:14px; margin:0; color:#7ee787; }
header .meta { color:#8b949e; }
header label { color:#8b949e; cursor:pointer; }
.entry { border:1px solid #30363d; border-radius:4px; margin:0 0 .35rem;
         background:#161b22; }
.entry summary { cursor:pointer; padding:.4rem .6rem; display:grid;
  grid-template-columns: 11ch 5ch 5ch 6ch 1fr 8ch; gap:.75rem;
  align-items:center; list-style:none; }
.entry summary::-webkit-details-marker { display:none; }
.entry[open] summary { border-bottom:1px solid #30363d; }
.ts   { color:#8b949e; font-size:11px; }
.method { font-weight:600; color:#d2a8ff; }
.status { font-weight:600; }
.status.s2xx { color:#7ee787; }
.status.s4xx { color:#f0883e; }
.status.s5xx { color:#ff7b72; }
.ms   { color:#8b949e; text-align:right; }
.path { color:#79c0ff; overflow:hidden; text-overflow:ellipsis;
        white-space:nowrap; }
.size { color:#8b949e; text-align:right; font-size:11px; }
.body { padding:.5rem .75rem; border-top:1px dashed #30363d; }
.body h3 { font-size:11px; margin:.4rem 0 .2rem; color:#8b949e;
           text-transform:uppercase; letter-spacing:.04em; }
.body pre { background:#0d1117; border:1px solid #21262d; border-radius:3px;
            padding:.5rem .65rem; margin:0 0 .35rem; overflow:auto;
            max-height:30em; white-space:pre-wrap; word-break:break-all; }
.req { border-left:3px solid #58a6ff !important; }
.resp { border-left:3px solid #7ee787 !important; }
"""

_DASHBOARD_JS = """
const params = new URLSearchParams(location.search);
const auto = params.get('auto') !== '0';
document.getElementById('auto').checked = auto;
document.getElementById('auto').addEventListener('change', e => {
  params.set('auto', e.target.checked ? '1' : '0');
  location.search = params.toString();
});
if (auto) setTimeout(() => location.reload(), 5000);
"""


def _row_html(e: dict) -> str:
    status = int(e.get("status", 0) or 0)
    cls = "s5xx" if status >= 500 else "s4xx" if status >= 400 else "s2xx"
    ts = e.get("ts", "")
    path = e.get("path", "") + (f"?{e['query']}" if e.get("query") else "")
    size = f"{e.get('req_size', 0)}↑/{e.get('resp_size', 0)}↓"
    if "req_body" in e:
        body_html = f"""
  <h3>request · {html.escape(e.get('req_ct',''))}</h3>
  <pre class="req">{html.escape(e.get('req_body','') or '<empty>')}</pre>"""
    else:
        body_html = """
  <h3>request body</h3>
  <pre class="req">disabled; set BROKER_LOG_BODIES=1 to opt in</pre>"""
    return f"""<details class="entry">
<summary>
  <span class="ts">{html.escape(ts.replace('+00:00','Z')[11:19])}</span>
  <span class="method">{html.escape(e.get('method',''))}</span>
  <span class="status {cls}">{status}</span>
  <span class="ms">{e.get('ms',0)}ms</span>
  <span class="path">{html.escape(path)}</span>
  <span class="size">{size}</span>
</summary>
<div class="body">
{body_html}
</div>
</details>"""


def render_dashboard() -> HTMLResponse:
    entries = _read_recent_entries()
    rows = "\n".join(_row_html(e) for e in reversed(entries))
    body = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>broker · dashboard</title>
<style>{_DASHBOARD_CSS}</style>
</head><body>
<header>
  <h1>broker · last {len(entries)} requests</h1>
  <span class="meta">log: {html.escape(str(LOG_FILE))}</span>
  <label><input type="checkbox" id="auto"> auto-refresh 5s</label>
</header>
{rows or '<p style="color:#8b949e">no requests logged yet — make one to populate</p>'}
<script>{_DASHBOARD_JS}</script>
</body></html>"""
    return HTMLResponse(body)
