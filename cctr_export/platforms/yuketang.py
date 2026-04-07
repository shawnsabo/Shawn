"""雨课堂题库平台"""
from typing import Optional, Callable
from .base import BasePlatform, Question, QuestionTypeEnum, register_platform


@register_platform("yuketang")
class YukeTangPlatform(BasePlatform):
    """
    雨课堂（https://yuketang.cn）
    清华大学 + 微软联合开发，高校广泛使用
    特点：随堂测试实时推送，课件内嵌测验
    """
    platform_name = "yuketang"

    def __init__(self):
        self._cookies: dict = {}

    def login(self, school_id: str, username: str, password: str) -> None:
        import httpx
        # 雨课堂登录通过 OAuth（清华账号体系或机构SSO）
        # TODO: 实现 actual login flow
        # URL: POST https://yuketang.cn/prod/2019/login
        # 参数: username, password, school_id
        self._cookies = {}

    def get_courses(self) -> list[dict]:
        # TODO: GET https://yuketang.cn/prod/2019/course/list
        # 返回: [{"course_id": "...", "name": "...", "classroom_id": "..."}]
        return []

    def get_questions(
        self,
        course_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        # TODO: 获取课件内嵌测验 + 随堂测试记录
        # 注意：雨课堂题目多有图片/富媒体，HTML 渲染需特殊处理
        return []

    def logout(self) -> None:
        self._cookies = {}
