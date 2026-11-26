"""图形验证码本地 OCR 识别（基于 ddddocr，单实例复用 + 预处理兜底）"""
from __future__ import annotations

import io
import re
import threading
from typing import Optional

_ocr_lock = threading.Lock()
_infer_lock = threading.Lock()
_ocr_instance = None
_ocr_import_checked = False
_ocr_available_flag = False


def is_ocr_available() -> bool:
    """检查当前环境是否可用 ddddocr。"""
    global _ocr_import_checked, _ocr_available_flag
    if _ocr_import_checked:
        return _ocr_available_flag
    with _ocr_lock:
        if not _ocr_import_checked:
            try:
                import ddddocr  # noqa: F401
                _ocr_available_flag = True
            except Exception:
                _ocr_available_flag = False
            _ocr_import_checked = True
    return _ocr_available_flag


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


def _clean_code(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (text or "")).strip()


def _upscale_grayscale_png(img_bytes: bytes) -> Optional[bytes]:
    """当原始 OCR 长度异常时，做 2x 放大灰度对比度增强作为备选输入。"""
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(img_bytes)) as im:
            gray = im.convert("L")
            scaled = gray.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)
            enhanced = ImageOps.autocontrast(scaled)
            buf = io.BytesIO()
            enhanced.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


def recognize_captcha(img_bytes: bytes, expected_len: int = 4, uppercase: bool = False) -> str:
    """识别图片验证码中的字母数字；若不可用则返回空字符串。"""
    if not img_bytes or not is_ocr_available():
        return ""

    ocr = _get_ocr()
    with _infer_lock:
        raw_code = _clean_code(ocr.classification(img_bytes))

    if len(raw_code) != expected_len:
        enhanced = _upscale_grayscale_png(img_bytes)
        if enhanced:
            with _infer_lock:
                alt_code = _clean_code(ocr.classification(enhanced))
            if len(alt_code) == expected_len or (not raw_code and alt_code):
                raw_code = alt_code

    return raw_code.upper() if uppercase else raw_code


def recognize_single_char(img_bytes: bytes) -> str:
    """识别单个混淆字体渲染汉字（用于超星学习通 font-cxsecret 与雨课堂字体还原）。"""
    if not img_bytes or not is_ocr_available():
        return ""
    ocr = _get_ocr()
    with _infer_lock:
        res = str(ocr.classification(img_bytes) or "").strip()
    return res[:1] if res else ""
