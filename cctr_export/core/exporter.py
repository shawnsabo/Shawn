"""题目导出引擎：A4 无损 PDF、分类 ZIP（含校验清单）与 PNG 图片导出"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from .http_utils import ResilientHttpSession, sniff_image_mime
from .integrity import (
    VERIFY_AND_SLICE_JS,
    build_export_document_html,
    safe_archive_segment,
    sha256_bytes,
    validate_questions,
)
from .kernels import detect_kernel, get_preferred_kernel, resolve_render_backend
from .models import Option, Question

_REMOTE_IMG_ATTR_RE = re.compile(
    r'(<img\b[^>]*?\bsrc\s*=\s*["\'])(https?://(?:[a-z0-9-]+\.)*(?:cctrcloud\.net|aliyuncs\.com)(?::(?:80|443))?/[^"\']+)(["\'])',
    re.I,
)


def _norm_img_url(url: str) -> str:
    u = url.strip()
    if u.lower().startswith("http://"):
        return "https://" + u[len("http://"):]
    return u


def prefetch_and_inline_images(questions: list[Question]) -> list[Question]:
    """直连并发预拉取允许域的远程图片并转为 data URI，避免无头浏览器受代理抖动影响且避免重复下载。"""
    raw_urls: list[str] = []
    seen_raw: set[str] = set()
    for q in questions:
        fields = [q.subject_html, q.answer, q.analysis_html] + [o.html for o in q.options]
        for fld in fields:
            if not fld or "://" not in fld:
                continue
            for m in _REMOTE_IMG_ATTR_RE.finditer(fld):
                u = m.group(2).strip()
                if u not in seen_raw:
                    seen_raw.add(u)
                    raw_urls.append(u)

    if not raw_urls:
        return questions

    fetch_urls = list(dict.fromkeys(_norm_img_url(u) for u in raw_urls))
    tls = threading.local()
    sessions: list[ResilientHttpSession] = []
    sessions_lock = threading.Lock()

    def _get_session() -> ResilientHttpSession:
        sess = getattr(tls, "sess", None)
        if sess is None:
            sess = ResilientHttpSession(timeout=20.0, prefer_direct=True)
            tls.sess = sess
            with sessions_lock:
                sessions.append(sess)
        return sess

    def _fetch_one(fetch_url: str) -> tuple[str, Optional[str]]:
        try:
            resp = _get_session().get(fetch_url, timeout=20.0, retries=2)
            if resp.status_code != 200 or not resp.content:
                return fetch_url, None
            mime = sniff_image_mime(resp.content)
            if not mime and resp.content.lstrip()[:64].lower().startswith((b"<svg", b"<?xml")):
                mime = "image/svg+xml"
            if not mime:
                return fetch_url, None
            b64 = base64.b64encode(resp.content).decode("ascii")
            return fetch_url, f"data:{mime};base64,{b64}"
        except Exception:
            return fetch_url, None

    fetch_map: dict[str, str] = {}
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(fetch_urls))) as pool:
            for fu, data_uri in pool.map(_fetch_one, fetch_urls):
                if data_uri:
                    fetch_map[fu] = data_uri
    finally:
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass

    if not fetch_map:
        return questions

    raw_map: dict[str, str] = {}
    for ru in raw_urls:
        nu = _norm_img_url(ru)
        if nu in fetch_map:
            raw_map[ru] = fetch_map[nu]

    if not raw_map:
        return questions

    def _inline_field(text: str) -> str:
        if not text or "://" not in text:
            return text
        return _REMOTE_IMG_ATTR_RE.sub(
            lambda m: f"{m.group(1)}{raw_map.get(m.group(2).strip(), m.group(2))}{m.group(3)}",
            text,
        )

    out: list[Question] = []
    for q in questions:
        new_opts = [
            Option(is_true=o.is_true, html=_inline_field(o.html))
            for o in q.options
        ]
        out.append(
            dataclasses.replace(
                q,
                subject_html=_inline_field(q.subject_html),
                answer=_inline_field(q.answer),
                analysis_html=_inline_field(q.analysis_html),
                options=new_opts,
            )
        )
    return out


def _find_chromium_binary(preferred_kind: Optional[str] = None) -> Optional[str]:
    """根据自选内核查找 Edge / Chrome / 便携 Chromium 可执行文件路径。"""
    kind = (preferred_kind or "auto").strip().lower()
    if kind in ("edge", "chrome", "chromium"):
        info = detect_kernel(kind)
        if info.installed and info.path and not info.path.startswith("builtin://"):
            return info.path
        return None
    for sub in ("edge", "chrome", "chromium"):
        info = detect_kernel(sub)
        if info.installed and info.path:
            return info.path
    return None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _render_pdf_via_cdp(html: str, binary_path: Optional[str] = None) -> bytes:
    """通过指定或本机 Edge/Chrome/Chromium Headless CDP 渲染 HTML 为 A4 PDF，并执行完整性校验。"""
    exe = binary_path or _find_chromium_binary()
    if not exe:
        raise RuntimeError("未找到可用的 Edge / Chrome / Chromium 内核，无法渲染 PDF")
    with _CdpSession(exe) as sess:
        return sess.render_pdf(html)


class _CdpSession:
    """复用单个 Headless Chromium/Edge/Chrome 进程，高效安全渲染多份 A4 PDF。"""

    def __init__(self, exe: str):
        self.exe = exe
        self.user_data: Optional[Path] = None
        self.proc = None
        self.ws = None
        self.seq = 0

    def __enter__(self):
        import httpx
        import websocket

        port = _pick_free_port()
        self.user_data = Path(tempfile.mkdtemp(prefix="cctr_pdf_profile_"))
        cmd = [
            self.exe,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.user_data}",
            "--window-size=658,1122",
            "about:blank",
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ws_url = None
        deadline = time.time() + 25.0
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("无头浏览器进程意外退出")
            try:
                targets = httpx.get(f"http://127.0.0.1:{port}/json", timeout=2.0, trust_env=False).json()
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.15)
        if not ws_url:
            raise RuntimeError("无头浏览器 CDP 端点未就绪")

        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Emulation.setEmulatedMedia", {"media": "print"})
        self.call("Emulation.setDeviceMetricsOverride", {"width": 658, "height": 1122, "deviceScaleFactor": 1, "mobile": False})
        return self

    def call(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        cid = self.seq
        self.ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == cid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} 失败: {msg['error']}")
                return msg.get("result", {})

    def render_pdf(self, html: str, idx: int = 0) -> bytes:
        assert self.user_data is not None
        html_file = self.user_data / f"doc_{idx}.html"
        html_file.write_text(html, encoding="utf-8")
        try:
            self.call("Page.navigate", {"url": html_file.as_uri()})
            for _ in range(120):
                st = self.call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True})
                if st.get("result", {}).get("value") == "complete":
                    break
                time.sleep(0.05)

            check = self.call(
                "Runtime.evaluate",
                {"expression": VERIFY_AND_SLICE_JS, "returnByValue": True, "awaitPromise": True},
            )
            val = check.get("result", {}).get("value") or {}
            if not val.get("ok"):
                raise RuntimeError(val.get("error") or "PDF 内容完整性校验失败")

            pdf_res = self.call(
                "Page.printToPDF",
                {
                    "printBackground": True,
                    "preferCSSPageSize": True,
                    "paperWidth": 8.27,
                    "paperHeight": 11.69,
                },
            )
            b64 = pdf_res.get("data", "")
            if not b64:
                raise RuntimeError("PDF 渲染返回为空")
            return base64.b64decode(b64)
        finally:
            try:
                html_file.unlink(missing_ok=True)
            except Exception:
                pass

    def __exit__(self, *_args):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        if self.user_data is not None:
            shutil.rmtree(self.user_data, ignore_errors=True)


# ── Qt WebEngine 主线程桥接器（零外部浏览器依赖） ──────────────────────
_qt_bridge = None


def init_qt_pdf_bridge(parent=None):
    """在主线程 QApplication 上注册 QWebEnginePage PDF 渲染桥。"""
    global _qt_bridge
    if _qt_bridge is not None:
        return _qt_bridge
    try:
        from PySide6.QtCore import QMarginsF, QObject, QTimer, QUrl, Qt, Signal, Slot
        from PySide6.QtGui import QPageLayout, QPageSize
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication
    except Exception:
        return None

    if QApplication.instance() is None:
        return None

    class _QtPdfBridge(QObject):
        _request = Signal(str, object)  # (html, state_dict)

        def __init__(self, p=None):
            super().__init__(p)
            self._request.connect(self._on_render)

        def render_pdf(self, html: str, timeout_s: float = 180.0) -> bytes:
            ev = threading.Event()
            state = {"event": ev, "pdf": None, "error": None}
            self._request.emit(html, state)
            if not ev.wait(timeout_s):
                raise RuntimeError("WebEngine PDF 渲染超时")
            if state["error"]:
                raise RuntimeError(state["error"])
            return state["pdf"]

        @Slot(str, object)
        def _on_render(self, html: str, state: dict):
            ev: threading.Event = state["event"]
            view = QWebEngineView()
            view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            view.resize(700, 1122)
            view.show()
            page = view.page()
            settings = page.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

            fd_html, html_p = tempfile.mkstemp(suffix=".html", prefix="cctr_doc_")
            os.close(fd_html)
            tmp_html_path = Path(html_p)
            tmp_html_path.write_text(html, encoding="utf-8")

            finished = {"done": False}

            def finish(pdf_bytes: bytes | None = None, err: str | None = None):
                if finished["done"]:
                    return
                finished["done"] = True
                state["pdf"] = pdf_bytes
                state["error"] = err
                try:
                    tmp_html_path.unlink(missing_ok=True)
                except Exception:
                    pass
                view.close()
                view.deleteLater()
                ev.set()

            def on_pdf_done(_path: str, ok: bool, tmp_path: Path):
                try:
                    if not ok or not tmp_path.exists():
                        finish(err="WebEngine 打印 PDF 失败")
                        return
                    data = tmp_path.read_bytes()
                    finish(pdf_bytes=data)
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass

            def start_verify():
                wrap_js = (
                    "window.__cctr_verify_res = '';"
                    f"({VERIFY_AND_SLICE_JS.strip().rstrip(';')})"
                    ".then(r => { window.__cctr_verify_res = JSON.stringify(r || {ok:false,error:'空校验结果'}); })"
                    ".catch(e => { window.__cctr_verify_res = JSON.stringify({ ok: false, error: String(e) }); });"
                )
                page.runJavaScript(wrap_js)

                timer = QTimer(page)
                attempts = {"n": 0}

                def poll():
                    if finished["done"]:
                        timer.stop()
                        return
                    attempts["n"] += 1
                    if attempts["n"] > 1200:
                        timer.stop()
                        finish(err="图片解码或排版校验超时")
                        return

                    def on_val(res):
                        if not res or finished["done"]:
                            return
                        if isinstance(res, str):
                            try:
                                res = json.loads(res)
                            except Exception:
                                return
                        timer.stop()
                        if not isinstance(res, dict) or not res.get("ok"):
                            finish(err=(res or {}).get("error") or "PDF 内容完整性校验失败")
                            return
                        fd, p = tempfile.mkstemp(suffix=".pdf", prefix="cctr_we_")
                        os.close(fd)
                        tmp_path = Path(p)
                        layout = QPageLayout(
                            QPageSize(QPageSize.PageSizeId.A4),
                            QPageLayout.Orientation.Portrait,
                            QMarginsF(18, 18, 18, 18),
                            QPageLayout.Unit.Millimeter,
                        )
                        page.pdfPrintingFinished.connect(lambda path, ok: on_pdf_done(path, ok, tmp_path))
                        page.printToPdf(str(tmp_path), layout)

                    page.runJavaScript("window.__cctr_verify_res || ''", on_val)

                timer.timeout.connect(poll)
                timer.start(50)

            page.loadFinished.connect(lambda ok: start_verify() if ok else finish(err="HTML 内容加载失败"))
            page.load(QUrl.fromLocalFile(str(tmp_html_path)))

    _qt_bridge = _QtPdfBridge(parent)
    return _qt_bridge


def render_html_to_pdf_bytes(html: str, kernel: Optional[str] = None) -> bytes:
    """将安全 HTML 渲染为经过图片解码、长图切片与页宽溢出校验的标准 A4 PDF 字节流。"""
    mode = (kernel or get_preferred_kernel() or "auto").strip().lower()
    if mode in ("edge", "chrome", "chromium"):
        backend, bin_path, _ = resolve_render_backend(mode)
        return _render_pdf_via_cdp(html, binary_path=bin_path)

    if mode == "auto":
        backend, bin_path, _ = resolve_render_backend("auto")
        if backend == "cdp" and bin_path:
            return _render_pdf_via_cdp(html, binary_path=bin_path)

    bridge = init_qt_pdf_bridge()
    if bridge is not None:
        return bridge.render_pdf(html)
    return _render_pdf_via_cdp(html)


def export_questions_to_pdf(
    questions: list[Question],
    output_dir: str | Path,
    driver_pool=None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    variant: str = "withAnswersRed",
    browser_type=None,
    kernel: Optional[str] = None,
    title: str = "题目与答案",
    filename: str = "output.pdf",
    smart_pagination: bool = True,
) -> Path:
    """导出合并的单个 A4 PDF（通过内容完整性、图片解码、长图切片与页宽校验）。"""
    items = prefetch_and_inline_images(validate_questions(questions))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback(0, len(items))

    eff_kernel = kernel or (str(browser_type).lower() if browser_type else None)
    html = build_export_document_html(items, variant=variant, title=title, smart_pagination=smart_pagination)
    pdf_bytes = render_html_to_pdf_bytes(html, kernel=eff_kernel)
    safe_name = filename if filename.lower().endswith(".pdf") else f"{filename}.pdf"
    pdf_path = out / safe_name
    pdf_path.write_bytes(pdf_bytes)

    if progress_callback:
        progress_callback(len(items), len(items))
    return pdf_path


def _unique_name_allocator():
    scopes: dict[str, tuple[dict[str, str], set[str]]] = {}

    def allocate(parent: str, original: str) -> str:
        if parent not in scopes:
            scopes[parent] = ({}, set())
        mapping, used = scopes[parent]
        if original in mapping:
            return mapping[original]
        base = safe_archive_segment(original)
        cand = base
        n = 2
        while cand.lower() in used:
            cand = f"{base} ({n})"
            n += 1
        mapping[original] = cand
        used.add(cand.lower())
        return cand

    return allocate


def export_questions_to_archive_zip(
    questions: list[Question],
    zip_path: str | Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    variant: str = "withAnswersRed",
    kernel: Optional[str] = None,
    smart_pagination: bool = True,
) -> Path:
    """按 学科/章节/题型 分类导出多个 PDF 并打包 ZIP，附带含 SHA-256 的 导出清单.json。"""
    items = prefetch_and_inline_images(validate_questions(questions))
    groups: dict[tuple[str, str, str], list[Question]] = defaultdict(list)
    for q in items:
        key = (q.subject_name or "未分类学科", q.chapter_name or "未分类章节", q.question_type or "未分类题型")
        groups[key].append(q)

    allocate = _unique_name_allocator()
    manifest = {
        "version": 1,
        "variant": variant,
        "questionCount": len(items),
        "groups": [],
    }
    zip_out = Path(zip_path)
    zip_out.parent.mkdir(parents=True, exist_ok=True)

    done = 0
    total = len(items)
    if progress_callback:
        progress_callback(0, total)

    eff_mode = (kernel or get_preferred_kernel() or "auto").strip().lower()
    backend, bin_path, _ = resolve_render_backend(eff_mode)

    def _write_groups(render_fn):
        nonlocal done
        with zipfile.ZipFile(str(zip_out), "w", zipfile.ZIP_DEFLATED) as zf:
            for g_idx, ((subj, chap, qtype), grp_items) in enumerate(groups.items()):
                s_dir = allocate("", subj)
                c_dir = allocate(s_dir, chap)
                parent = f"{s_dir}/{c_dir}"
                t_name = allocate(parent, qtype)
                rel_path = f"{parent}/{t_name}.pdf"

                doc_title = f"{subj} / {chap} / {qtype}"
                html = build_export_document_html(grp_items, variant=variant, title=doc_title, smart_pagination=smart_pagination)
                pdf_bytes = render_fn(html, g_idx)
                zf.writestr(rel_path, pdf_bytes)

                manifest["groups"].append({
                    "subject": subj,
                    "chapter": chap,
                    "type": qtype,
                    "path": rel_path,
                    "count": len(grp_items),
                    "questionIds": [q.id for q in grp_items],
                    "sha256": sha256_bytes(pdf_bytes),
                })
                done += len(grp_items)
                if progress_callback:
                    progress_callback(done, total)

            zf.writestr("导出清单.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

    if backend == "cdp" and bin_path:
        with _CdpSession(bin_path) as sess:
            _write_groups(lambda html, g_idx: sess.render_pdf(html, idx=g_idx))
    else:
        _write_groups(lambda html, _g_idx: render_html_to_pdf_bytes(html, kernel="builtin"))

    return zip_out


def export_questions_to_images(
    questions: list[Question],
    output_dir: str | Path,
    driver_pool=None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    variant: str = "withAnswersRed",
    browser_type=None,
    kernel: Optional[str] = None,
) -> Path:
    """导出题目为 PNG 图片（基于自选或自动检测 Chromium/Edge/Chrome CDP 单题高清截图）。"""
    import httpx
    import websocket

    items = prefetch_and_inline_images(validate_questions(questions))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    eff_kernel = kernel or (str(browser_type).lower() if browser_type else get_preferred_kernel())
    exe = _find_chromium_binary(eff_kernel)
    if not exe and eff_kernel == "builtin":
        exe = _find_chromium_binary("auto")
    if not exe:
        raise RuntimeError("未找到可用的 Edge / Chrome / Chromium 内核，无法渲染 PNG 图片；请在左侧选择并下载便携 Chromium")

    port = _pick_free_port()
    user_data = Path(tempfile.mkdtemp(prefix="cctr_img_profile_"))
    proc = subprocess.Popen(
        [
            exe, "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data}", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ws = None
    try:
        ws_url = None
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                targets = httpx.get(f"http://127.0.0.1:{port}/json", timeout=2.0, trust_env=False).json()
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        if not ws_url:
            raise RuntimeError("浏览器 CDP 未就绪")
        ws = websocket.create_connection(ws_url, timeout=60)
        seq = 0

        def call(method: str, params: dict | None = None) -> dict:
            nonlocal seq
            seq += 1
            cid = seq
            ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == cid:
                    return msg.get("result", {})

        call("Page.enable")
        call("Runtime.enable")
        for idx, q in enumerate(items, 1):
            html = build_export_document_html([q], variant=variant, title=f"第 {idx} 题")
            tmp_html = user_data / f"q_{idx}.html"
            tmp_html.write_text(html, encoding="utf-8")
            call("Emulation.setDeviceMetricsOverride", {"width": 860, "height": 400, "deviceScaleFactor": 2, "mobile": False})
            call("Page.navigate", {"url": tmp_html.as_uri()})
            for _ in range(50):
                st = call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True})
                if st.get("result", {}).get("value") == "complete":
                    break
                time.sleep(0.05)
            chk = call("Runtime.evaluate", {"expression": VERIFY_AND_SLICE_JS, "returnByValue": True, "awaitPromise": True})
            val = chk.get("result", {}).get("value") or {}
            if not val.get("ok"):
                raise RuntimeError(val.get("error") or f"第 {idx} 题图片校验失败")
            h_res = call("Runtime.evaluate", {"expression": "Math.ceil(document.body.scrollHeight)", "returnByValue": True})
            full_h = max(200, int(h_res.get("result", {}).get("value") or 400))
            call("Emulation.setDeviceMetricsOverride", {"width": 860, "height": full_h, "deviceScaleFactor": 2, "mobile": False})
            shot = call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            (out / f"q_{idx:04d}.png").write_bytes(base64.b64decode(shot["data"]))
            if progress_callback:
                progress_callback(idx, len(items))
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(user_data, ignore_errors=True)
    return out


def pack_to_zip(source_dir: str | Path, zip_path: str | Path) -> Path:
    """将目录打包为 ZIP"""
    source_dir = Path(source_dir)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source_dir.rglob("*")):
            if file.is_file():
                zf.write(str(file), str(file.relative_to(source_dir)))
    return zip_path
