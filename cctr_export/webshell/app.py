"""QWebEngine 外壳：加载 Tauri 前端 + 本地 API 服务 + 原生验证码对话框"""
import json
import sys
import threading

from PySide6.QtCore import QObject, Signal, QUrl, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView

from . import backend_api, captcha
from .server import start_server


class _EventPump(QObject):
    """工作线程事件 → Qt 主线程 → 页面 shim 派发"""
    eventReceived = Signal(str, str)

    def __init__(self, page):
        super().__init__()
        self._page = page
        self._ready = False
        self.eventReceived.connect(self._dispatch)

    def mark_ready(self):
        self._ready = True

    def emit(self, event, payload):
        self.eventReceived.emit(event, json.dumps(payload, ensure_ascii=False, default=str))

    def _dispatch(self, event, payload_json):
        if not self._ready:
            return
        self._page.runJavaScript(
            f"window.__tauri_shim__.emitEvent({json.dumps(event)}, {payload_json});"
        )


class _CaptchaDialogBridge(QObject):
    """工作线程请求 → 主线程弹原生验证码对话框 → 结果回传"""
    request = Signal(bytes, str)

    def __init__(self):
        super().__init__()
        self._done = threading.Event()
        self._result = ""
        self.request.connect(self._show)

    def ask(self, png_bytes, title):
        self._done.clear()
        self._result = ""
        self.request.emit(png_bytes, title)
        self._done.wait(300)
        return self._result

    def _show(self, png_bytes, title):
        dlg = QDialog()
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        tip = QLabel("登录需要图形验证码。安装 ddddocr 后将自动识别。")
        tip.setStyleSheet("color:#606266;font-size:12px;")
        img = QLabel()
        pix = QPixmap.fromImage(QImage.fromData(png_bytes))
        img.setPixmap(pix.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation))
        inp = QLineEdit()
        inp.setPlaceholderText("输入图中 4 位字符")
        btn = QPushButton("确定")

        def _ok():
            self._result = inp.text().strip()
            dlg.accept()

        btn.clicked.connect(_ok)
        inp.returnPressed.connect(_ok)
        lay.addWidget(tip)
        lay.addWidget(img)
        lay.addWidget(inp)
        lay.addWidget(btn)
        dlg.exec()
        self._done.set()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)

    view = QWebEngineView()
    view.setWindowTitle("CCTRCloud Export")
    view.resize(1280, 860)

    pump = _EventPump(view.page())
    captcha.set_dialog_handler(_CaptchaDialogBridge().ask)
    backend_api.set_event_emitter(pump.emit)

    srv, port = start_server(backend_api)
    view.load(QUrl(f"http://127.0.0.1:{port}/"))
    view.loadFinished.connect(lambda ok: pump.mark_ready())
    view.show()
    return app.exec()
