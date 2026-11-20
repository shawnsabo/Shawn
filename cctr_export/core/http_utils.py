"""HTTP 工具与图片格式校验（支持代理自动回退与图片魔数识别）"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0"}


def sniff_image_mime(data: bytes) -> Optional[str]:
    """根据二进制魔数判断图片 MIME 类型，非图片返回 None。"""
    if not data or len(data) < 8:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 14 and data[:2] == b"BM":
        return "image/bmp"
    return None


def make_http_client(*, trust_env: bool = False, timeout: float = 30.0) -> httpx.Client:
    """安全创建 httpx.Client（隔离 SOCKS 缺包等代理异常）。"""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        trust_env=trust_env,
        headers=dict(_DEFAULT_HEADERS),
    )


class ResilientHttpSession:
    """带代理回退与瞬态重试的 HTTP 会话，跨请求保留 Cookie（如 PHPSESSID / 4A17_seccode）。"""

    def __init__(
        self,
        timeout: float = 30.0,
        prefer_direct: bool = True,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self._timeout = timeout
        self._prefer_direct = prefer_direct
        self._trust_env = not prefer_direct
        self._log_fn = log_fn
        self._client = self._create_initial_client()

    def _log(self, msg: str) -> None:
        if self._log_fn:
            self._log_fn(msg)
        else:
            logger.debug(msg)

    def _create_initial_client(self) -> httpx.Client:
        try:
            return make_http_client(trust_env=self._trust_env, timeout=self._timeout)
        except Exception as exc:
            self._log(f"[http] 初始化 Client(trust_env={self._trust_env}) 失败，回退另一模式: {exc!r}")
            self._trust_env = not self._trust_env
            return make_http_client(trust_env=self._trust_env, timeout=self._timeout)

    @property
    def cookies(self) -> httpx.Cookies:
        return self._client.cookies

    def _switch_proxy_mode(self) -> bool:
        alt_trust_env = not self._trust_env
        try:
            new_client = make_http_client(trust_env=alt_trust_env, timeout=self._timeout)
        except Exception as exc:
            self._log(f"[http] 切换代理模式(trust_env={alt_trust_env})失败: {exc!r}")
            return False
        new_client.cookies.update(self._client.cookies)
        try:
            self._client.close()
        except Exception:
            pass
        self._client = new_client
        self._trust_env = alt_trust_env
        self._log(f"[http] 已切换网络模式: trust_env={self._trust_env}")
        return True

    def request(
        self,
        method: str,
        url: str,
        *,
        retries: int = 1,
        **kwargs,
    ) -> httpx.Response:
        """执行请求；遇到传输/代理错误时先同模式重试，必要时自动切换直连/系统代理。"""
        kwargs.setdefault("timeout", self._timeout)
        last_exc: Optional[BaseException] = None
        switched = False

        for attempt in range(max(1, retries + 1)):
            try:
                resp = self._client.request(method, url, **kwargs)
                return resp
            except (httpx.TransportError, ImportError, OSError) as exc:
                last_exc = exc
                self._log(f"[http] 请求异常(attempt={attempt + 1}, trust_env={self._trust_env}): {exc!r}")
                if not switched and self._switch_proxy_mode():
                    switched = True
                    continue
                if attempt < retries:
                    time.sleep(0.25 * (attempt + 1))

        assert last_exc is not None
        raise last_exc

    def get(self, url: str, *, retries: int = 2, **kwargs) -> httpx.Response:
        return self.request("GET", url, retries=retries, **kwargs)

    def post(self, url: str, *, retries: int = 0, **kwargs) -> httpx.Response:
        return self.request("POST", url, retries=retries, **kwargs)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
