"""题库平台基类 + 统一数据模型"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum


class QuestionTypeEnum(str, Enum):
    SINGLE = "single"       # 单选题
    MULTIPLE = "multiple"   # 多选题
    JUDGE = "judge"          # 判断题
    FILL = "fill"           # 填空题
    ESSAY = "essay"         # 简答题/论述题


@dataclass
class Option:
    """统一选项模型"""
    label: str               # 选项标签 A/B/C/D
    html: str                # 选项内容（HTML）
    is_true: bool = False    # 是否为正确答案


@dataclass
class Question:
    """统一题目模型 — 所有平台共用"""
    platform: str                             # 平台标识
    external_id: str                          # 平台原始题目 ID
    question_type: str                        # 原始题型名
    question_type_enum: QuestionTypeEnum      # 标准题型枚举
    subject_html: str                         # 题目正文
    answer_html: str                          # 答案解析
    options: list[Option] = field(default_factory=list)  # 选项（可为空）
    chapter: str = ""                         # 所属章节
    difficulty: int = 3                       # 难度 1-5
    tags: list[str] = field(default_factory=list)         # 标签
    has_options: bool = True                  # 是否有选项

    def __post_init__(self):
        if not isinstance(self.question_type_enum, QuestionTypeEnum):
            self.question_type_enum = QuestionTypeEnum.SINGLE

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "external_id": self.external_id,
            "question_type": self.question_type,
            "question_type_enum": self.question_type_enum.value,
            "subject_html": self.subject_html,
            "answer_html": self.answer_html,
            "options": [
                {"label": o.label, "html": o.html, "is_true": o.is_true}
                for o in self.options
            ],
            "chapter": self.chapter,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "has_options": self.has_options,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        options = [Option(**o) for o in d.get("options", [])]
        return cls(
            platform=d["platform"],
            external_id=d["external_id"],
            question_type=d["question_type"],
            question_type_enum=QuestionTypeEnum(d.get("question_type_enum", "single")),
            subject_html=d["subject_html"],
            answer_html=d["answer_html"],
            options=options,
            chapter=d.get("chapter", ""),
            difficulty=d.get("difficulty", 3),
            tags=d.get("tags", []),
            has_options=d.get("has_options", bool(options)),
        )


# ─────────────────────────────────────────
# 平台注册装饰器
# ─────────────────────────────────────────

_PLATFORM_REGISTRY: dict[str, type["BasePlatform"]] = {}


def register_platform(name: str):
    """平台注册装饰器"""
    def deco(cls: type["BasePlatform"]) -> type["BasePlatform"]:
        _PLATFORM_REGISTRY[name] = cls
        cls.platform_name = name
        return cls
    return deco


class PlatformRegistry:
    """平台注册表（静态方法集合）"""

    @staticmethod
    def list() -> list[str]:
        return list(_PLATFORM_REGISTRY.keys())

    @staticmethod
    def get(name: str) -> type["BasePlatform"]:
        return _PLATFORM_REGISTRY.get(name)

    @staticmethod
    def all() -> dict[str, type["BasePlatform"]]:
        return dict(_PLATFORM_MSG := _PLATFORM_REGISTRY)


# ─────────────────────────────────────────
# 平台基类
# ─────────────────────────────────────────

class BasePlatform(ABC):
    """
    题库平台抽象基类。
    新增平台只需：
      1. 继承 BasePlatform
      2. 用 @register_platform("xxx") 装饰
      3. 实现所有 @abstractmethod
    """

    platform_name: str = "base"  # 由装饰器填充

    @abstractmethod
    def login(self, school_id: str, username: str, password: str) -> None:
        """登录平台，保存认证状态"""
        raise NotImplementedError

    @abstractmethod
    def get_courses(self) -> list[dict]:
        """
        获取课程/练习列表。
        返回格式: [{"id": "...", "name": "...", "type": "...", ...}]
        """
        raise NotImplementedError

    @abstractmethod
    def get_questions(
        self,
        course_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        """
        获取指定课程的题目列表。
        progress_callback(current, total) 用于进度报告。
        """
        raise NotImplementedError

    @abstractmethod
    def logout(self) -> None:
        """退出登录，清理认证状态"""
        raise NotImplementedError

    def to_export_format(self, questions: list[Question]) -> list[dict]:
        """
        转换为导出格式（与现有 exporter 兼容）。
        默认返回与 core/models.py Question 兼容的字典。
        """
        return [q.to_dict() for q in questions]
