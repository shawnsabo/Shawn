"""platforms/ — 多题库平台注册与统一数据模型"""
from .base import BasePlatform, Question, Option, PlatformRegistry, register_platform

__all__ = ["BasePlatform", "Question", "Option", "PlatformRegistry", "register_platform"]
