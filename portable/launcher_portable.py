"""CCTRCloud Export Portable — 单文件版启动核心

内嵌：原版 Rust exe + WebView2Loader.dll（PyInstaller --add-binary 注入）
启动流程：内存补丁(URL 等长替换 + RSA 公钥等长替换) → 释放到临时目录 →
          启动 Rust 应用(WebView2 CDP) → 本地代理(8899, 登录自动补验证码) →
          辅助服务(8898) → CDP 注入验证码行 → OCR 自动识别(ddddocr)
"""
import base64
import faulthandler
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

# ── 崩溃诊断 ──
faulthandler.enable()
LOG_PATH = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CCTRPortable" / "portable.log"


def log(msg):
    line = time.strftime("[%H:%M:%S] ") + str(msg)
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _excepthook(tp, val, tb):
    log("EXCEPTION: " + "".join(traceback.format_exception(tp, val, tb)))


sys.excepthook = _excepthook
threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback)

# ── 常量 ──
API_PORT = 8899
HELPER_PORT = 8898
CDP_PORT = 9222
REAL = "https://api.cctrcloud.net"
REAL_BASE = REAL + "/mobile/index.php"

OLD_URL = b"https://api.cctrcloud.net/mobile/index.php"
NEW_URL = b"http://127.0.0.1:8899/mobile/index.php????"
OLD_KEY = (b"MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDDLyh5Lb/5TprGvS9yFCcpCYnb0"
           b"FuSyY3+TPbJI7Pv3+u4eFoqGGN46qyFOVLhUuFRttMfoA8h8yrdYCssLi93baoByT"
           b"MYf5/KVlviLKXWd3TDOJdeSX4d+qLUp/WK0ckm2VaJuY5vW0x5x6WbZ8MSxwTDMqN"
           b"NMgVUdOgD3MIScwIDAQAB")
NEW_KEY = (b"MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDO3r40irpueBqKoCSh01YG8qhX"
           b"XH10pgZje98q7ZvjOWad/da8Eejrbs3uyNOEwYmFJckUA8X0MiGOr3Mlv1VAXTA9"
           b"T9YxbBObkLNUMj2VWLbjgZNiDzZwqeprLVvIbQSLSEUseVf/EmdCeEgMOzxnahsK"
           b"KIs7u+iN13xPFBY0kwIDAQAB")

INJECTOR_JS = r"""
(function () {
  "use strict";
  if (window.__cctr_captcha_installed) return;
  window.__cctr_captcha_installed = true;
  var ROW_ID = "__cctr_captcha_row";
  var HELPER = "http://127.0.0.1:8898";
  var reloading = false;
  function findForm() {
    return document.querySelector(".wizard-body .form") || document.querySelector(".form");
  }
  function findPasswordInput() {
    var labels = document.querySelectorAll(".form label");
    for (var i = 0; i < labels.length; i++) {
      if (labels[i].querySelector('input[type="password"]')) return labels[i];
    }
    return null;
  }
  function ensureUI() {
    if (document.getElementById(ROW_ID)) return true;
    var form = findForm();
    if (!form || !findPasswordInput()) return false;
    var row = document.createElement("div");
    row.id = ROW_ID;
    row.style.cssText = "margin-top:2px;display:grid;gap:7px;";
    row.innerHTML =
      '<span style="color:#334155;font-size:13px;font-weight:650;">验证码（自动识别中，可不填）</span>' +
      '<div style="display:flex;gap:10px;align-items:center;">' +
      '<input id="__cctr_captcha_input" maxlength="8" autocomplete="off" placeholder="自动识别失败时手动输入"' +
      ' style="flex:1;min-height:40px;border:1px solid var(--line);border-radius:8px;' +
      'background:var(--surface);color:var(--ink);padding:0 12px;outline:none;" />' +
      '<img id="__cctr_captcha_img" alt="验证码加载中" title="点击图片刷新"' +
      ' style="height:40px;min-width:110px;border:1px solid var(--line);border-radius:8px;' +
      'cursor:pointer;background:#fff;" />' +
      "</div>";
    form.appendChild(row);
    var input = row.querySelector("#__cctr_captcha_input");
    var img = row.querySelector("#__cctr_captcha_img");
    input.addEventListener("input", function () {
      fetch(HELPER + "/code", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: input.value }) }).catch(function () {});
    });
    img.addEventListener("click", function () { reload(); });
    syncDisabled();
    reload();
    return true;
  }
  function syncDisabled() {
    var row = document.getElementById(ROW_ID);
    if (!row) return;
    var pwd = findPasswordInput();
    var input = row.querySelector("input");
    if (pwd && input) input.disabled = pwd.disabled;
  }
  function reload() {
    if (reloading) return;
    reloading = true;
    fetch(HELPER + "/captcha").then(function (r) { return r.json(); }).then(function (res) {
      var img2 = document.getElementById("__cctr_captcha_img");
      if (img2 && res && res.image) img2.src = res.image;
      reloading = false;
    }).catch(function () { reloading = false; });
  }
  var lastAuthSeq = null;
  setInterval(function () {
    fetch(HELPER + "/authstate").then(function (r) { return r.json(); }).then(function (s) {
      if (lastAuthSeq === null) { lastAuthSeq = s.seq; return; }
      if (s.seq !== lastAuthSeq) {
        lastAuthSeq = s.seq;
        var input = document.getElementById("__cctr_captcha_input");
        if (input) input.value = "";
        reload();
      }
    }).catch(function () {});
  }, 1200);
  var mo = new MutationObserver(function () {
    if (!ensureUI()) return;
    syncDisabled();
    ensureBrand();
  });
  function ensureBrand() {
    if (document.getElementById("__cctr_brand")) return;
    var b = document.createElement("div");
    b.id = "__cctr_brand";
    b.textContent = "Designed by Silvite and Shawnmark";
    b.style.cssText = "position:fixed;left:12px;bottom:10px;z-index:2147483000;" +
      "font-size:11px;font-weight:600;letter-spacing:.2px;pointer-events:none;user-select:none;" +
      "color:rgba(232,246,243,.72);text-shadow:0 1px 2px rgba(0,0,0,.35);";
    document.body.appendChild(b);
  }
  function start() {
    ensureUI();
    ensureBrand();
    mo.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
"""

# ── OCR（ddddocr，实例复用） ──
_ocr_instance = None
_ocr_lock = threading.Lock()


def _ocr_available():
    try:
        import ddddocr  # noqa: F401
        return True
    except ImportError:
        return False


def _get_ocr():
    global _ocr_instance
    with _ocr_lock:
        if _ocr_instance is None:
            import ddddocr
            try:
                _ocr_instance = ddddocr.DdddOcr(show_ad=False)
            except TypeError:
                _ocr_instance = ddddocr.DdddOcr()
        return _ocr_instance


def _ocr_solve(img: bytes) -> str:
    code = _get_ocr().classification(img)
    return re.sub(r"[^A-Za-z0-9]", "", (code or ""))


# ── 会话池 + 代理 ──
class SessionPool:
    def __init__(self, debug_dir: Path):
        self._lock = threading.Lock()
        self.by_sid = {}
        self.current = None
        self.code = None
        self.auth_seq = 0
        self.debug_dir = debug_dir
        self.dialog_handler = None  # fn(png, title) -> str（主线程 tkinter）
        self.ocr_fail_streak = 0

    def set_dialog_handler(self, fn):
        self.dialog_handler = fn

    def _new_client(self):
        return httpx.Client(timeout=60, follow_redirects=True,
                            headers={"User-Agent": "Mozilla/5.0"})

    def _fetch_captcha_image(self, client) -> bytes:
        r = client.get(REAL_BASE + "?act=seccode&op=makecode&t=" + str(time.time()))
        r.raise_for_status()
        return r.content

    def prepare_captcha(self) -> str:
        with self._lock:
            client = self.current or self._new_client()
            self.current = client
            self.code = None
        img = self._fetch_captcha_image(client)
        return "data:image/png;base64," + base64.b64encode(img).decode("ascii")

    def set_code(self, code: str):
        with self._lock:
            self.code = (code or "").strip()

    def _debug_save(self, img: bytes, code: str):
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            n = len(list(self.debug_dir.glob("*.png")))
            if n < 80:
                (self.debug_dir / f"{int(time.time()*1000)}_{code or 'unread'}.png").write_bytes(img)
        except Exception:
            pass

    def solve_captcha(self, client) -> str:
        """单次求解：注入码优先；OCR 自动（连败 3 次后插入手工窗口）"""
        with self._lock:
            typed = self.code
            self.code = None
        if typed:
            return typed
        if _ocr_available():
            img = self._fetch_captcha_image(client)
            code = _ocr_solve(img)
            self._debug_save(img, code)
            if not code:
                raise RuntimeError("OCR 未识别出 4 位验证码")
            if self.ocr_fail_streak >= 3 and self.dialog_handler:
                # 连败保护：请人工确认一张
                self.ocr_fail_streak = 0
                manual = self.dialog_handler(img, "验证码人工确认（自动识别连续失败）")
                return (manual or code)
            return code
        deadline = time.time() + 20
        while time.time() < deadline:
            with self._lock:
                if self.code:
                    code = self.code
                    self.code = None
                    return code
            time.sleep(0.5)
        img = self._fetch_captcha_image(client)
        if self.dialog_handler:
            return self.dialog_handler(img, "登录验证码")
        raise RuntimeError("无法获取验证码输入")

    def forward(self, method, path_qs, headers, body):
        path_qs = path_qs.replace("????", "")  # 剥离补丁垫片
        cookies_in = headers.get("Cookie") or ""
        psid = None
        for part in cookies_in.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "PHPSESSID":
                psid = v
                break
        with self._lock:
            if psid and psid in self.by_sid:
                client = self.by_sid[psid]
            elif self.current is not None:
                client = self.current
            else:
                client = self._new_client()
        is_login = "act=login" in path_qs and "op=getschoolData" not in path_qs
        if is_login:
            orig_body = body
            last_resp = None
            for attempt in range(6):
                code = self.solve_captcha(client)
                variant = code.upper() if attempt % 2 == 1 else code
                body = (orig_body or b"") + ("&captcha=" + urllib.parse.quote(variant)).encode("utf-8")
                log(f"login attempt {attempt+1}: captcha={variant}")
                resp = client.request(method, REAL + path_qs, content=body,
                                      headers={"Content-Type": headers.get("Content-Type",
                                               "application/x-www-form-urlencoded")},
                                      timeout=60)
                captcha_error = False
                try:
                    j = resp.json()
                    err = j.get("datas", {}).get("error", "") if isinstance(j.get("datas"), dict) else ""
                    captcha_error = "验证码" in str(err)
                except Exception:
                    captcha_error = False
                if not captcha_error:
                    self.ocr_fail_streak = 0
                    return resp
                self.ocr_fail_streak += 1
                last_resp = resp
            return last_resp

        resp = client.request(method, REAL + path_qs, content=body,
                              headers={"Content-Type": headers.get("Content-Type",
                                       "application/x-www-form-urlencoded")},
                              timeout=60)
        new_psid = client.cookies.get("PHPSESSID")
        if new_psid:
            with self._lock:
                self.by_sid[new_psid] = client
                self.current = client
        return resp


class ProxyHandler(BaseHTTPRequestHandler):
    pool: SessionPool = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _reply(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        try:
            resp = self.pool.forward(self.command, self.path, dict(self.headers), body)
            self.send_response(resp.status_code)
            self.send_header("Content-Type",
                             resp.headers.get("Content-Type", "application/octet-stream"))
            self.send_header("Content-Length", str(len(resp.content)))
            for sc in resp.headers.get_list("set-cookie"):
                self.send_header("Set-Cookie", sc)
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            payload = json.dumps({"code": 400, "datas": {"error": f"本地代理：{e}"}}).encode("utf-8")
            self._reply(200, payload, "application/json; charset=utf-8")

    do_GET = _handle
    do_POST = _handle
    do_OPTIONS = _handle


class HelperHandler(BaseHTTPRequestHandler):
    pool: SessionPool = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/captcha":
            try:
                self._reply(200, {"ok": True, "image": self.pool.prepare_captcha()})
            except Exception as e:
                self._reply(200, {"ok": False, "error": str(e)})
            return
        if path == "/authstate":
            with self.pool._lock:
                seq = self.pool.auth_seq
            self._reply(200, {"ok": True, "seq": seq})
            return
        if path == "/health":
            self._reply(200, {"ok": True})
            return
        self._reply(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            args = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            args = {}
        if path == "/code":
            self.pool.set_code(str(args.get("code", "")))
            self._reply(200, {"ok": True})
            return
        self._reply(404, {"ok": False, "error": "not found"})


def start_servers(pool, api_port=API_PORT, helper_port=HELPER_PORT):
    api_srv = ThreadingHTTPServer(("127.0.0.1", api_port),
                                  type("_P", (ProxyHandler,), {"pool": pool}))
    helper_srv = ThreadingHTTPServer(("127.0.0.1", helper_port),
                                     type("_H", (HelperHandler,), {"pool": pool}))
    for srv in (api_srv, helper_srv):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return api_srv, helper_srv


# ── CDP 客户端 ──
class CDPClient:
    def __init__(self, port):
        import websocket
        self.port = port
        self.ws = None
        self.seq = 0
        self.lock = threading.Lock()

    def connect(self, timeout_s=90):
        import websocket
        deadline = time.time() + timeout_s
        page = None
        while time.time() < deadline and page is None:
            try:
                targets = httpx.get(f"http://127.0.0.1:{self.port}/json", timeout=5).json()
                pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
                if pages:
                    page = pages[0]
                    break
            except Exception:
                pass
            time.sleep(1.0)
        if page is None:
            raise RuntimeError("CDP 端点未就绪")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": "Runtime.enable"}))
        self._recv_until(self.seq, 15)
        log("[cdp] attached: " + page.get("title", "")[:50])

    def _recv_until(self, want, timeout_s=30):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.time()))
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                continue
            if isinstance(msg, dict) and msg.get("id") == want:
                return msg
        raise TimeoutError("CDP 响应超时")

    def eval(self, expr, timeout_s=30):
        with self.lock:
            self.seq += 1
            i = self.seq
            self.ws.send(json.dumps({"id": i, "method": "Runtime.evaluate",
                                     "params": {"expression": expr, "returnByValue": True,
                                                "awaitPromise": False}}))
            return self._recv_until(i, timeout_s)


# ── tkinter 验证码对话框（无 OCR 连败时的兜底，轻量无 PySide6） ──
class TkDialogBridge:
    def __init__(self, root, req_queue):
        self.root = root
        self.req_queue = req_queue
        self._done = threading.Event()
        self._result = ""

    def ask(self, png_bytes, title):
        self._done.clear()
        self._result = ""
        self.req_queue.put((png_bytes, title))
        self._done.wait(30)
        return self._result

    def pump(self):
        try:
            while True:
                png_bytes, title = self.req_queue.get_nowait()
                self._show(png_bytes, title)
        except queue.Empty:
            pass
        self.root.after(120, self.pump)

    def _show(self, png_bytes, title):
        try:
            import tkinter as tk
            w = tk.Toplevel(self.root)
            w.title(title)
            w.attributes("-topmost", True)
            tk.Label(w, text="登录需要图形验证码（已自动获取）。").pack(padx=12, pady=(10, 4))
            ph = tk.PhotoImage(data=base64.b64encode(png_bytes).decode("ascii"))
            lbl = tk.Label(w, image=ph)
            lbl.image = ph
            lbl.pack(padx=12, pady=4)
            e = tk.Entry(w, width=16)
            e.pack(padx=12, pady=6)
            holder = {"code": ""}

            def _ok():
                holder["code"] = e.get().strip()
                w.destroy()

            btn = tk.Button(w, text="确定", command=_ok)
            btn.pack(pady=(2, 10))
            w.protocol("WM_DELETE_WINDOW", w.destroy)
            e.focus_set()

            def _wait():
                self._result = holder["code"]
                self._done.set()

            w.bind("<Destroy>", lambda _ev: _wait())
            e.bind("<Return>", lambda _ev: _ok())
        except Exception as e:
            log("tkdialog error: " + repr(e))
            self._done.set()


# ── 补丁与释放 ──
def resource_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def patch_bytes(data: bytes) -> bytes:
    n_url, n_key = data.count(OLD_URL), data.count(OLD_KEY)
    if n_url != 1 or n_key != 1:
        raise RuntimeError(f"补丁目标计数异常：URL={n_url} KEY={n_key}")
    return data.replace(OLD_URL, NEW_URL).replace(OLD_KEY, NEW_KEY)


def prepare_workspace() -> tuple[Path, Path]:
    """释放内嵌原版 exe/dll → 内存补丁 → 写入本次运行工作目录"""
    base = resource_dir()
    work = Path(tempfile.gettempdir()) / f"cctr_portable_{os.getpid()}"
    work.mkdir(parents=True, exist_ok=True)
    src = base / "CCTRCloudExportRust-v3.exe"
    data = src.read_bytes()
    patched = patch_bytes(data)
    exe = work / "CCTRCloudExportRust-v3-proxy.exe"
    exe.write_bytes(patched)
    dll = base / "WebView2Loader.dll"
    if dll.exists():
        shutil.copy2(dll, work / "WebView2Loader.dll")
    # 清理历史残留临时目录
    for old in Path(tempfile.gettempdir()).glob("cctr_portable_*"):
        if old != work:
            shutil.rmtree(old, ignore_errors=True)
    return exe, work


def main():
    log("=== CCTRCloud Export Portable 启动 ===")

    # 单实例：辅助端口被占 = 已有实例在跑
    try:
        pool = SessionPool(debug_dir=Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                           / "CCTRPortable" / "captcha_debug")
        start_servers(pool)
    except OSError as e:
        print("端口被占用（程序可能已在运行）：", e)
        return 1

    try:
        exe, work = prepare_workspace()
        log("[release] 已释放并补丁 Rust 应用 → " + str(work))
    except Exception as e:
        log("释放/补丁失败: " + repr(e))
        return 1

    env = os.environ.copy()
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={CDP_PORT}"
    proc = subprocess.Popen([str(exe)], cwd=str(work), env=env)
    log(f"[launch] Rust 应用已启动（PID {proc.pid}）")

    import tkinter as tk
    root = tk.Tk()
    root.title("CCTRCloud Export - 后台服务")
    root.withdraw()  # 服务窗不外显；关闭 Rust 主窗口时整套自动退出

    req_queue = queue.Queue()
    bridge = TkDialogBridge(root, req_queue)
    pool.set_dialog_handler(bridge.ask)

    def watchdog():
        cdp = CDPClient(CDP_PORT)
        try:
            cdp.connect()
            source = INJECTOR_JS
            while True:
                time.sleep(3)
                if proc.poll() is not None:
                    log("[launcher] Rust 应用已退出")
                    root.after(0, root.destroy)
                    return
                r = cdp.eval("window.__TAURI_INTERNALS__ ? '1' : '0'", timeout_s=10)
                if r.get("result", {}).get("result", {}).get("value") != "1":
                    continue
                installed = cdp.eval("window.__cctr_captcha_installed === true ? '1' : '0'",
                                     timeout_s=10).get("result", {}).get("result", {}).get("value")
                if installed != "1":
                    cdp.eval(source, timeout_s=20)
                    log("[inject] 验证码行已注入")
                row = cdp.eval("(!!document.getElementById('__cctr_captcha_row')) ? '1' : '0'",
                               timeout_s=10).get("result", {}).get("result", {}).get("value")
                if row != "1":
                    cdp.eval("window.__cctr_captcha_ensure && window.__cctr_captcha_ensure()", timeout_s=10)
        except Exception as e:
            log("[watchdog] 退出: " + str(e)[:150])
            root.after(0, root.destroy)

    threading.Thread(target=watchdog, daemon=True).start()
    bridge.pump()
    root.mainloop()
    try:
        proc.kill()
    except Exception:
        pass
    log("=== 退出 ===")
    return 0


if __name__ == "__main__":
    INJECTOR_JS = INJECTOR_JS  # 内嵌于上方常量
    sys.exit(main())
