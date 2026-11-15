"""本地 HTTP 服务：静态前端（注入 shim）+ /api 命令通道"""
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


def _index_html() -> bytes:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    marker = '<script type="module"'
    shim = ('<script src="/tauri_shim.js"></script>\n    '
            '<script src="/captcha_inject.js"></script>\n    ')
    if marker not in html:
        raise RuntimeError("index.html 结构与预期不符（未找到 module script 标记）")
    return html.replace(marker, shim + marker, 1).encode("utf-8")


def _shim_js() -> bytes:
    return (Path(__file__).resolve().parent / "shim_source.js").read_bytes()


def _inject_js() -> bytes:
    return (Path(__file__).resolve().parent / "captcha_inject.js").read_bytes()


class _Handler(BaseHTTPRequestHandler):
    backend = None  # 由 start_server 注入
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _reply(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._reply(200, _index_html(), "text/html; charset=utf-8")
            return
        if path == "/tauri_shim.js":
            self._reply(200, _shim_js(), "text/javascript; charset=utf-8")
            return
        if path == "/captcha_inject.js":
            self._reply(200, _inject_js(), "text/javascript; charset=utf-8")
            return
        rel = path.lstrip("/")
        f = (FRONTEND_DIR / rel).resolve()
        if str(f).startswith(str(FRONTEND_DIR)) and f.is_file():
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            self._reply(200, f.read_bytes(), ctype)
        else:
            self._reply(404, b"not found", "text/plain")

    def do_POST(self):
        path = self.path.split("?")[0]
        if not path.startswith("/api/"):
            self._reply(404, json.dumps({"ok": False, "error": "not found"}).encode("utf-8"),
                        "application/json; charset=utf-8")
            return
        cmd = path[len("/api/"):]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            args = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            args = {}
        try:
            data = self.backend.dispatch(cmd, args)
            body = json.dumps({"ok": True, "data": data}, ensure_ascii=False, default=str).encode("utf-8")
        except Exception as e:
            body = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode("utf-8")
        self._reply(200, body, "application/json; charset=utf-8")


def start_server(backend, host="127.0.0.1", port=0):
    """启动本地服务，返回 (server, port)。仅绑定回环地址。"""
    handler_cls = type("_BoundHandler", (_Handler,), {"backend": backend})
    srv = ThreadingHTTPServer((host, port), handler_cls)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, srv.server_address[1]
