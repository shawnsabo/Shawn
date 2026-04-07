"""学习通(超星)题库平台"""
from typing import Optional, Callable
from .base import BasePlatform, Question, QuestionTypeEnum, register_platform


@register_platform("xuexitong")
class XueXiTongPlatform(BasePlatform):
    """
    学习通（超星尔雅移动端，https://chaoxing.com）
    高校通识课大量使用，题库封闭性强，题目随机组卷
    注意：超星对账号风控严格，建议控制请求频率
    """
    platform_name = "xuexitong"

    def __init__(self):
        self._uid: str = ""
        self._enc: str = ""  # 超星加密 token

    def login(self, school_id: str, username: str, password: str) -> None:
        import httpx
        # 超星登录：POST https://passport2.chaoxing.com/fanyalogin
        # 参数: uname, password(md5), schoolid
        # 返回: uid, _uid, enc
        self._uid = ""
        self._enc = ""

    def get_courses(self) -> list[dict]:
        # TODO: GET https://mooc2-ans.chaoxing.com/clazz/getStuCourseInfo
        return []

    def get_questions(
        self,
        course_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        # 超星题目获取难点：题目分批推送，需模拟答题过程
        # 可参考：通过历史答题记录获取
        return []

    def logout(self) -> None:
        self._uid = ""
        self._enc = ""
