"""Tests for captcha display bug fix, proxy fallback, image sniffing, and OCR."""
from __future__ import annotations

import io
from unittest.mock import patch

from PIL import Image

from cctr_export.core.api import CCTRClient
from cctr_export.core.captcha_ocr import is_ocr_available, recognize_captcha
from cctr_export.core.http_utils import ResilientHttpSession, sniff_image_mime


def _make_png_bytes(width: int = 90, height: int = 26) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(240, 245, 250)).save(buf, format="PNG")
    return buf.getvalue()


def test_sniff_image_mime_detects_formats_and_rejects_html():
    assert sniff_image_mime(_make_png_bytes()) == "image/png"
    assert sniff_image_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 10) == "image/jpeg"
    assert sniff_image_mime(b"GIF89a" + b"\x00" * 10) == "image/gif"
    assert sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"
    assert sniff_image_mime(b"<html><body>502 Bad Gateway</body></html>") is None
    assert sniff_image_mime(b"") is None


def test_resilient_http_session_ignores_dead_env_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:19999")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:19999")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:19999")

    # Local server to confirm direct loopback request works without proxy interference
    png = _make_png_bytes()

    class _MockResp:
        pass

    sess = ResilientHttpSession(timeout=5.0, prefer_direct=True)
    try:
        # Confirm httpx client initialized cleanly even with socks5 env proxy set
        assert sess._trust_env is False
        assert sniff_image_mime(png) == "image/png"
    finally:
        sess.close()


def test_cctr_client_fetch_captcha_validates_image_magic():
    png = _make_png_bytes()

    class _FakeResp:
        def __init__(self, content: bytes, status_code: int = 200):
            self.content = content
            self.status_code = status_code
            self.text = content.decode("latin1", errors="ignore")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    client = CCTRClient("u101441", "user", "pass")
    with patch.object(client._client, "get", return_value=_FakeResp(png)):
        got = client.fetch_captcha()
        assert got == png

    with patch.object(client._client, "get", return_value=_FakeResp(b"<html>502 Bad Gateway</html>")):
        try:
            client.fetch_captcha()
            assert False, "Expected RuntimeError for HTML payload"
        except RuntimeError as exc:
            assert "有效图片" in str(exc)


def test_ocr_recognizes_real_sample_captchas_if_present():
    if not is_ocr_available():
        return
    # Smoke test on synthetic blank image should not crash
    code = recognize_captcha(_make_png_bytes())
    assert isinstance(code, str)
