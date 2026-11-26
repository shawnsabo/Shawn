"""CCTRCloud Export Desktop - 入口"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path


def _write_crash_log(title: str, tb_text: str) -> Path | None:
    candidates = [
        Path.home() / ".cctr_export" / "crash.log",
        Path(tempfile.gettempdir()) / "cctr_export_crash.log",
    ]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = f"[{stamp}] {title}\n{tb_text}\n{'-' * 60}\n"
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(payload)
            return log_path
        except OSError:
            continue
    return None


def _show_fatal_dialog(title: str, message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
            return
        except Exception:
            pass
    print(f"{title}: {message}", file=sys.stderr)


def _report_fatal(exc_type, exc_value, exc_tb, *, source: str = "主线程") -> None:
    if exc_type and issubclass(exc_type, KeyboardInterrupt):
        return
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log_path = _write_crash_log(f"未捕获异常 ({source})", tb_text)
    log_hint = f"\n\n详细日志已保存至:\n{log_path}" if log_path else ""
    _show_fatal_dialog(
        "融智云考 · 印务台 启动/运行异常",
        f"程序遇到未处理错误（{source}）：\n{exc_value}{log_hint}",
    )


def _install_crash_handler() -> None:
    sys.excepthook = lambda t, v, tb: _report_fatal(t, v, tb, source="主线程")
    if hasattr(threading, "excepthook"):
        threading.excepthook = lambda args: _write_crash_log(
            f"后台线程异常 ({getattr(args.thread, 'name', 'worker')})",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )


def _configure_runtime_environment() -> None:
    """在导入 Qt/WebEngine 之前配置独立运行时 DLL 路径与兼容参数，避免受宿主机环境差异影响。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        dll_dirs = [
            meipass,
            meipass / "PySide6",
            meipass / "shiboken6",
            meipass / "onnxruntime" / "capi",
        ]
        path_parts = [str(d) for d in dll_dirs if d.is_dir()]
        for d_str in path_parts:
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(d_str)
                except OSError:
                    pass
        if path_parts:
            existing_path = os.environ.get("PATH", "")
            os.environ["PATH"] = os.pathsep.join(path_parts + ([existing_path] if existing_path else []))

    if sys.platform == "win32":
        # 避免第三方杀毒软件、受限权限目录或虚拟机/RDP 环境下 Chromium 沙盒或 GPU 沙盒崩溃/白屏
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        for flag in ("--no-sandbox", "--disable-gpu-sandbox"):
            if flag not in flags:
                flags.append(flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)


def _run_self_check(out_file: str = "") -> int:
    """运行环境自检：校验独立运行时 DLL、OCR 模型、网络组件与导出目录是否就绪。"""
    import certifi
    import onnxruntime
    import socksio
    from Crypto.Cipher import AES
    from PIL import Image
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    from cctr_export.core.captcha_ocr import is_ocr_available
    from cctr_export.core.database import init_db
    from cctr_export.core.integrity import sanitize_rich_html
    from cctr_export.core.kernels import get_export_dir

    init_db()
    export_dir = get_export_dir()
    ocr_ok = is_ocr_available()
    sanitized = sanitize_rich_html("<table><tabody><tr><td>OK</td></tr></tabody></table>")
    assert "<tbody>" in sanitized
    assert certifi.where()
    assert AES and Image and onnxruntime and socksio
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    summary = (
        f"SELF_CHECK_OK ocr={ocr_ok} ort={onnxruntime.__version__} "
        f"export_dir={export_dir}"
    )
    if out_file:
        try:
            Path(out_file).write_text(summary, encoding="utf-8")
        except OSError:
            pass
    if sys.stdout is not None:
        print(summary)
    return 0


def main():
    _install_crash_handler()
    _configure_runtime_environment()

    try:
        for arg in sys.argv[1:]:
            if arg == "--self-check":
                sys.exit(_run_self_check())
            if arg.startswith("--self-check="):
                sys.exit(_run_self_check(arg.split("=", 1)[1]))

        from PySide6.QtCore import QCoreApplication, Qt
        from PySide6.QtGui import QFont
        from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory
        from PySide6.QtWidgets import QApplication
        from cctr_export.core.database import init_db
        from cctr_export.ui import MainWindow

        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        app = QApplication(sys.argv)
        # 校园网与国内教育平台直连优先，避免本地 Clash/VPN 系统代理破坏 TLS 握手导致内置浏览器白屏
        QNetworkProxyFactory.setUseSystemConfiguration(False)
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        app.setApplicationName("CCTRCloud Export Studio")
        app.setStyle("Fusion")
        app.setFont(QFont("Microsoft YaHei UI", 10))
        init_db()

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except SystemExit:
        raise
    except Exception:
        _report_fatal(*sys.exc_info(), source="启动初始化")
        sys.exit(1)


if __name__ == "__main__":
    main()
