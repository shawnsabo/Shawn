"""QWebEngineView + QWebChannel 桌面工作台桥接器（1:1 Figma Studio 视觉界面 + 本地 Python 引擎）"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QFile, QIODevice, QObject, QSize, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMainWindow

from ..core.api import CCTRClient
from ..core.captcha_ocr import is_ocr_available, recognize_captcha
from ..core.database import (
    ExportType,
    TaskStatus,
    add_task,
    clear_all_logs,
    delete_task,
    get_all_logs,
    get_all_tasks,
    update_task_status,
)
from ..core.exporter import init_qt_pdf_bridge
from ..core.kernels import (
    KERNEL_LABELS,
    cleanup_empty_legacy_output_dirs,
    detect_all_kernels,
    download_and_install_kernel,
    get_export_dir,
    get_preferred_kernel,
    load_settings,
    save_settings,
    set_export_dir,
    set_preferred_kernel,
)
from ..core.models import ChapterType, Practice, QuestionType
from ..core.tasks import engine


def _build_atelier_icon() -> QIcon:
    """绘制 Editorial Atelier 裁切十字标应用图标。"""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor("#141413"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    pen = QPen(QColor("#FAF9F6"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap)
    painter.setPen(pen)
    # 四角裁切线
    painter.drawLine(14, 14, 23, 14)
    painter.drawLine(14, 14, 14, 23)
    painter.drawLine(50, 14, 41, 14)
    painter.drawLine(50, 14, 50, 23)
    painter.drawLine(14, 50, 23, 50)
    painter.drawLine(14, 50, 14, 41)
    painter.drawLine(50, 50, 41, 50)
    painter.drawLine(50, 50, 50, 41)
    # 中心十字准星
    painter.drawLine(32, 22, 32, 42)
    painter.drawLine(22, 32, 42, 32)
    painter.end()
    return QIcon(pix)


def _resolve_web_index() -> Path:
    local = Path(__file__).resolve().parent / "web" / "index.html"
    if local.exists():
        return local
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "cctr_export" / "ui" / "web" / "index.html"
        if bundled.exists():
            return bundled
    raise FileNotFoundError("未找到桌面端前端资源 web/index.html")


def _task_artifact_path(t) -> Path | None:
    if getattr(t, "output_path", ""):
        recorded = Path(t.output_path)
        if recorded.exists():
            return recorded
    base = Path.home() / ".cctr_export" / "output"
    if t.export_type == ExportType.ZIP:
        p = base / f"task_{t.id}_categorized.zip"
    elif t.export_type == ExportType.IMG:
        p = base / f"task_{t.id}_images.zip"
    else:
        p = base / str(t.id) / "output.pdf"
    return p if p.exists() else None


def _fmt_size(p: Path | None) -> str:
    if p is None or not p.exists():
        return ""
    b = p.stat().st_size
    if b >= 1048576:
        return f"{b / 1048576:.1f} MB"
    return f"{max(1, b // 1024)} KB"


def get_saved_accounts() -> list[dict[str, str]]:
    """读取常用账号记忆（仅存学校代码与学号，绝不落盘密码）；未初始化时从历史任务去重导入。"""
    settings = load_settings()
    raw_list = settings.get("saved_accounts")
    accounts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(sch: str, usr: str):
        s, u = (sch or "").strip(), (usr or "").strip()
        if not s or not u or (s, u) in seen:
            return
        seen.add((s, u))
        accounts.append({"school": s, "username": u})

    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict):
                _add(str(item.get("school", "")), str(item.get("username", "")))
    else:
        try:
            for t in get_all_tasks():
                _add(t.school_id, t.username)
                if len(accounts) >= 6:
                    break
            if accounts:
                save_settings({"saved_accounts": accounts})
        except Exception:
            pass
    return accounts[:6]


def remember_saved_account(school: str, username: str) -> list[dict[str, str]]:
    """置顶并持久化最近成功登录的账号（仅学校代码与学号，最多保留 6 条）。"""
    s, u = (school or "").strip(), (username or "").strip()
    if not s or not u:
        return get_saved_accounts()
    cur = [x for x in get_saved_accounts() if not (x["school"] == s and x["username"] == u)]
    updated = ([{"school": s, "username": u}] + cur)[:6]
    save_settings({"saved_accounts": updated})
    return updated


def remove_saved_account(school: str, username: str) -> list[dict[str, str]]:
    s, u = (school or "").strip(), (username or "").strip()
    updated = [x for x in get_saved_accounts() if not (x["school"] == s and x["username"] == u)]
    save_settings({"saved_accounts": updated})
    return updated


class _CaptchaWorker(QThread):
    done = Signal(str)

    def __init__(self, client: CCTRClient):
        super().__init__()
        self._client = client

    def run(self):
        try:
            ocr_ready = is_ocr_available()
            data = self._client.fetch_captcha()
            b64 = base64.b64encode(data).decode("ascii")
            # 先立刻把验证码图片推送给前端展示，再异步/连续完成 OCR（避免冷启动首帧久等）
            if not ocr_ready:
                self.done.emit(
                    json.dumps(
                        {
                            "ok": True,
                            "imageDataUri": f"data:image/png;base64,{b64}",
                            "code": "",
                            "ocrAvailable": False,
                        },
                        ensure_ascii=False,
                    )
                )
                return

            code = ""
            for attempt in range(3):
                if attempt > 0:
                    data = self._client.fetch_captcha()
                    b64 = base64.b64encode(data).decode("ascii")
                try:
                    cand = recognize_captcha(data, expected_len=4)
                except Exception:
                    cand = ""
                if len(cand) == 4:
                    code = cand
                    break
            self.done.emit(
                json.dumps(
                    {
                        "ok": True,
                        "imageDataUri": f"data:image/png;base64,{b64}",
                        "code": code,
                        "ocrAvailable": ocr_ready,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            self.done.emit(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))


class _LoginWorker(QThread):
    done = Signal(str)

    def __init__(self, client: CCTRClient, captcha: str, auto_retry_ocr: bool):
        super().__init__()
        self._client = client
        self._captcha = captcha
        self._auto_retry_ocr = auto_retry_ocr

    def run(self):
        captcha = self._captcha
        max_attempts = 3 if (self._auto_retry_ocr and is_ocr_available()) else 1
        last_err = ""
        for attempt in range(max_attempts):
            if attempt > 0:
                captcha = ""
                for _ in range(3):
                    try:
                        img = self._client.fetch_captcha()
                        cand = recognize_captcha(img, expected_len=4)
                        if len(cand) == 4:
                            captcha = cand
                            break
                    except Exception:
                        pass
                if len(captcha) != 4:
                    break
            try:
                self._client.login(captcha=captcha)
                practices = self._client.get_practice_list()
                payload = [
                    {
                        "id": p.id,
                        "courseid": p.courseid,
                        "practise_id": p.practise_id,
                        "teacher_id": p.teacher_id,
                        "lesson_name": p.lesson_name,
                        "practice_name": p.practice_name,
                        "teacher_name": p.teacher_name,
                        "finish_time": p.finish_time,
                        "question_count": p.question_count,
                        "json": p.to_json(),
                    }
                    for p in practices
                ]
                self.done.emit(json.dumps({"ok": True, "practices": payload}, ensure_ascii=False))
                return
            except Exception as e:
                last_err = str(e)
                if "验证码" not in last_err:
                    break
        self.done.emit(json.dumps({"ok": False, "error": last_err or "登录失败"}, ensure_ascii=False))


class _FilterWorker(QThread):
    done = Signal(str)

    def __init__(self, client: CCTRClient, practice: Practice):
        super().__init__()
        self._client = client
        self._practice = practice

    def run(self):
        try:
            chapters, qtypes = self._client.get_chapter_and_question_type(self._practice)
            self.done.emit(
                json.dumps(
                    {
                        "ok": True,
                        "chapters": [c.to_dict() for c in chapters],
                        "question_types": [q.to_dict() for q in qtypes],
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            self.done.emit(json.dumps({"ok": False, "chapters": [], "question_types": [], "error": str(e)}, ensure_ascii=False))


class _KernelWorker(QThread):
    progress = Signal(int, str)
    done = Signal(str)

    def __init__(self, kind: str):
        super().__init__()
        self._kind = kind

    def run(self):
        try:
            info = download_and_install_kernel(
                self._kind,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.done.emit(
                json.dumps(
                    {"ok": True, "message": f"{info.name} ({info.version}) 已就绪", "kind": info.kind},
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            self.done.emit(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))


class DesktopBridge(QObject):
    captchaReady = Signal(str)
    loginDone = Signal(str)
    filtersReady = Signal(str)
    stateChanged = Signal(str)
    kernelProgress = Signal(int, str)
    kernelDone = Signal(str)
    windowStateChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client: CCTRClient | None = None
        self._workers: list[QThread] = []
        self._last_state_json = ""
        try:
            cleanup_empty_legacy_output_dirs()
        except Exception:
            pass
        # 后台预热 OCR 模型，打开界面后验证码秒级填充
        if is_ocr_available():
            threading.Thread(target=lambda: recognize_captcha(b""), daemon=True).start()

    def stop_workers(self):
        for w in list(self._workers):
            try:
                w.quit()
                w.wait(2000)
            except Exception:
                pass

    def _keep_worker(self, w: QThread):
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()

    def _ensure_client(self) -> CCTRClient:
        if self._client is None:
            self._client = CCTRClient("", "", "")
        return self._client

    def _kernels_payload(self) -> dict:
        all_k = detect_all_kernels()
        return {
            "preferred": get_preferred_kernel(),
            "labels": [{"key": k, "label": lbl} for k, lbl in KERNEL_LABELS],
            "items": {
                k: {
                    "kind": v.kind,
                    "name": v.name,
                    "installed": v.installed,
                    "path": v.path,
                    "version": v.version,
                    "source": v.source,
                    "can_download": v.can_download,
                }
                for k, v in all_k.items()
            },
        }

    def _tasks_and_logs_payload(self) -> dict:
        tasks = get_all_tasks()
        logs = get_all_logs(limit=120)
        task_list = []
        for t in tasks:
            art = _task_artifact_path(t)
            total_q = 0
            first_title = ""
            for idx_c, cfg in enumerate(t.config):
                try:
                    p = Practice.from_json(cfg["practice"])
                    if idx_c == 0:
                        first_title = p.lesson_name or p.practice_name
                    if p.question_count:
                        total_q += p.question_count
                except Exception:
                    pass
            if len(t.config) > 1 and first_title:
                summary_title = f"{first_title} 等{len(t.config)}项"
            else:
                summary_title = first_title or f"任务 #{t.id}"
            task_list.append(
                {
                    "id": t.id,
                    "title": summary_title,
                    "username": t.username,
                    "school_id": t.school_id,
                    "status": t.status.value,
                    "export_type": t.export_type.value,
                    "create_time": t.create_time[:19].replace("T", " "),
                    "file_path": str(art) if art else "",
                    "file_name": art.name if art else "",
                    "file_size": _fmt_size(art),
                    "question_count": total_q,
                }
            )
        return {"tasks": task_list, "logs": logs}

    @Slot(result=str)
    def getInitialState(self) -> str:
        settings = load_settings()
        payload = {
            "ocrAvailable": is_ocr_available(),
            "darkMode": bool(settings.get("dark_mode", False)),
            "exportDir": str(get_export_dir()),
            "savedAccounts": get_saved_accounts(),
            "kernels": self._kernels_payload(),
            **self._tasks_and_logs_payload(),
        }
        self._last_state_json = json.dumps(self._tasks_and_logs_payload(), ensure_ascii=False)
        return json.dumps(payload, ensure_ascii=False)

    def poll_state(self, force: bool = False):
        data = self._tasks_and_logs_payload()
        raw = json.dumps(data, ensure_ascii=False)
        if force or raw != self._last_state_json:
            self._last_state_json = raw
            self.stateChanged.emit(raw)

    @Slot()
    def fetchCaptcha(self):
        w = _CaptchaWorker(self._ensure_client())
        w.done.connect(self.captchaReady.emit)
        self._keep_worker(w)

    @Slot(str, str, str, str, bool)
    def login(self, school: str, username: str, password: str, captcha: str, auto_retry_ocr: bool):
        c = self._ensure_client()
        c.school_id = school.strip()
        c.username = username.strip()
        c.password = password.strip()
        w = _LoginWorker(c, captcha.strip(), auto_retry_ocr)

        def on_done(raw: str):
            try:
                data = json.loads(raw)
                if data.get("ok"):
                    data["savedAccounts"] = remember_saved_account(c.school_id, c.username)
                    raw = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
            self.loginDone.emit(raw)

        w.done.connect(on_done)
        self._keep_worker(w)

    @Slot(str, str, result=str)
    def removeSavedAccount(self, school: str, username: str) -> str:
        return json.dumps({"savedAccounts": remove_saved_account(school, username)}, ensure_ascii=False)

    @Slot(str)
    def loadFilters(self, practice_json: str):
        p = Practice.from_json(practice_json)
        w = _FilterWorker(self._ensure_client(), p)
        w.done.connect(self.filtersReady.emit)
        self._keep_worker(w)

    @Slot(str, result=str)
    def submitExport(self, payload_json: str) -> str:
        if not self._client or not self._client.key:
            return json.dumps({"ok": False, "error": "会话已失效，请重新登录"}, ensure_ascii=False)
        try:
            body = json.loads(payload_json)
            fmt = ExportType(body.get("format", "pdf"))
            variant = str(body.get("variant", "withAnswersRed"))
            practiced_only = bool(body.get("practicedOnly", False))
            smart_pagination = bool(body.get("smartPagination", True))
            chapters = [ChapterType.from_dict(c) for c in body.get("chapters", [])]
            qtypes = [QuestionType.from_dict(q) for q in body.get("questionTypes", [])]
            practices_json = body.get("practices", [])
            if not practices_json:
                return json.dumps({"ok": False, "error": "请至少选择一个练习"}, ensure_ascii=False)

            config = [
                {
                    "practice": pj,
                    "chapters": [c.to_dict() for c in chapters],
                    "question_types": [q.to_dict() for q in qtypes],
                    "variant": variant,
                    "practiced_only": practiced_only,
                    "smart_pagination": smart_pagination,
                }
                for pj in practices_json
            ]
            task_id = add_task(
                self._client.school_id,
                self._client.username,
                self._client.password,
                fmt,
                config,
                auth_key=self._client.key,
            )
            engine.run_task(task_id)
            self.poll_state(force=True)
            return json.dumps({"ok": True, "taskId": task_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    @Slot()
    def resetSession(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    @Slot(int)
    def runTask(self, task_id: int):
        update_task_status(task_id, TaskStatus.WAITING)
        engine.run_task(task_id)
        self.poll_state(force=True)

    @Slot(int)
    def deleteTask(self, task_id: int):
        delete_task(task_id)
        self.poll_state(force=True)

    @Slot()
    def clearLogs(self):
        clear_all_logs()
        self.poll_state(force=True)

    @Slot(int)
    def openTaskFile(self, task_id: int):
        for t in get_all_tasks():
            if t.id == task_id:
                art = _task_artifact_path(t)
                if art and art.exists():
                    self._open_local(art)
                    return
        self.openTaskDir(task_id)

    @Slot(int)
    def openTaskDir(self, task_id: int):
        for t in get_all_tasks():
            if t.id == task_id:
                art = _task_artifact_path(t)
                if art and art.exists():
                    if os.name == "nt":
                        subprocess.Popen(["explorer", "/select,", str(art)])
                    else:
                        self._open_local(art.parent)
                    return
        self.openExportDir()

    @Slot()
    def openExportDir(self):
        self._open_local(get_export_dir())

    @Slot(result=str)
    def chooseExportDir(self) -> str:
        current = str(get_export_dir())
        parent_w = self.parent() if isinstance(self.parent(), QMainWindow) else None
        chosen = QFileDialog.getExistingDirectory(parent_w, "选择默认导出保存文件夹", current)
        if not chosen:
            return json.dumps({"ok": False, "exportDir": current}, ensure_ascii=False)
        saved = set_export_dir(chosen)
        return json.dumps({"ok": True, "exportDir": str(saved)}, ensure_ascii=False)

    def _open_local(self, target: Path):
        if os.name == "nt":
            os.startfile(str(target))
        else:
            subprocess.Popen(["xdg-open", str(target)])

    @Slot(str, result=str)
    def selectKernel(self, kind: str) -> str:
        set_preferred_kernel(kind)
        return json.dumps(self._kernels_payload(), ensure_ascii=False)

    @Slot(result=str)
    def detectKernels(self) -> str:
        return json.dumps(self._kernels_payload(), ensure_ascii=False)

    @Slot(str)
    def downloadKernel(self, kind: str):
        target = "chromium" if kind == "auto" else kind
        w = _KernelWorker(target)
        w.progress.connect(self.kernelProgress.emit)

        def on_done(res_json: str):
            data = json.loads(res_json)
            data["kernels"] = self._kernels_payload()
            self.kernelDone.emit(json.dumps(data, ensure_ascii=False))

        w.done.connect(on_done)
        self._keep_worker(w)

    @Slot(bool)
    def setDarkMode(self, dark: bool):
        save_settings({"dark_mode": bool(dark)})

    def _main_win(self) -> QMainWindow | None:
        p = self.parent()
        return p if isinstance(p, QMainWindow) else None

    @Slot()
    def windowMinimize(self):
        w = self._main_win()
        if w:
            w.showMinimized()

    @Slot()
    def windowToggleMaximize(self):
        w = self._main_win()
        if not w:
            return
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    @Slot()
    def windowClose(self):
        w = self._main_win()
        if w:
            w.close()

    @Slot()
    def windowStartDrag(self):
        w = self._main_win()
        if w and w.windowHandle():
            w.windowHandle().startSystemMove()

    @Slot(str)
    def windowStartResize(self, edge: str):
        w = self._main_win()
        if not w or not w.windowHandle():
            return
        edge_map = {
            "n": Qt.Edge.TopEdge,
            "s": Qt.Edge.BottomEdge,
            "w": Qt.Edge.LeftEdge,
            "e": Qt.Edge.RightEdge,
            "nw": Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
            "ne": Qt.Edge.TopEdge | Qt.Edge.RightEdge,
            "sw": Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
            "se": Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
        }
        qt_edge = edge_map.get((edge or "").lower())
        if qt_edge is not None:
            w.windowHandle().startSystemResize(qt_edge)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CCTR Atelier · 融智云考印务工作台")
        self.setWindowIcon(_build_atelier_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self._dwm_applied = False
        self.setMinimumSize(QSize(680, 560))
        self.resize(1340, 840)

        screen = self.screen().availableGeometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

        # 主线程初始化内置 QtWebEngine PDF 打印桥（供内置/兜底模式使用）
        init_qt_pdf_bridge(self)

        self._view = QWebEngineView(self)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self._channel = QWebChannel(self._view.page())
        self._bridge = DesktopBridge(self)
        self._channel.registerObject("cctrBridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # 通过 QFile 内联注入 qwebchannel.js，避开 file:// 加载 qrc:// 跨域拦截
        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        if qwc_file.open(QIODevice.OpenModeFlag.ReadOnly):
            qwc_code = bytes(qwc_file.readAll()).decode("utf-8", errors="ignore")
            qwc_file.close()
            script = QWebEngineScript()
            script.setName("qwebchannel")
            script.setSourceCode(qwc_code)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(False)
            self._view.page().scripts().insert(script)

        self.setCentralWidget(self._view)

        index_html = _resolve_web_index()
        self._view.load(QUrl.fromLocalFile(str(index_html)))

        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self._bridge.poll_state(False))
        self._timer.start(1500)

    def _apply_win11_dwm_style(self):
        if self._dwm_applied or os.name != "nt":
            return
        self._dwm_applied = True
        try:
            class _MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]

            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), ctypes.sizeof(ctypes.c_int)
            )
            margins = _MARGINS(0, 0, 0, 1)
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_win11_dwm_style()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "_bridge"):
            self._bridge.windowStateChanged.emit(self.isMaximized())

    def closeEvent(self, event):
        self._bridge.stop_workers()
        engine.shutdown()
        super().closeEvent(event)
