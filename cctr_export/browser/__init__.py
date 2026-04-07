"""browser/ — 多浏览器自动检测与统一工厂"""
from .factory import detect_browser, create_driver, DriverPool

__all__ = ["detect_browser", "create_driver", "DriverPool"]
