"""验证码求解：优先本地 OCR（ddddocr，若已安装），否则弹原生对话框人工输入"""
import threading

_dialog_handler = None  # 由 app.py 注入（主线程弹窗、阻塞等输入）


def set_dialog_handler(fn):
    global _dialog_handler
    _dialog_handler = fn


def solve(png_bytes: bytes, title: str = "图形验证码") -> str:
    try:
        import ddddocr  # noqa: F401
        has_ocr = True
    except ImportError:
        has_ocr = False

    if has_ocr:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        code = ocr.classification(png_bytes)
        return (code or "").strip()

    if _dialog_handler is None:
        raise RuntimeError("无法显示验证码输入窗口（可安装 ddddocr 启用自动识别）")
    return _dialog_handler(png_bytes, title)
