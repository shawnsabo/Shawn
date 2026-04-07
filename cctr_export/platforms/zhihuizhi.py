"""智慧职教题库平台"""
from typing import Optional, Callable
from .base import BasePlatform, Question, Option, QuestionTypeEnum, register_platform


@register_platform("zhihuizhi")
class ZhihuizhiPlatform(BasePlatform):
    """
    智慧职教（https://www.icve.com.cn）
    支持：职教云课程练习/章节测验/期末考试
    """
    platform_name = "zhihuizhi"

    BASE_URL = "https://www.icve.com.cn"

    def __init__(self):
        self._token: str = ""
        self._user_id: str = ""

    def login(self, school_id: str, username: str, password: str) -> None:
        import httpx
        # 智慧职教使用 token 认证
        client = httpx.Client(timeout=60, follow_redirects=True)
        # TODO: 实现 actual login flow
        # 已知：POST /portal/login ajaxLogin
        # 参数: username, password(md5), schoolId
        self._token = ""  # placeholder
        self._user_id = ""
        client.close()

    def get_courses(self) -> list[dict]:
        # TODO: GET /portal/student/getMyCourseList
        # 返回: [{"id": "...", "name": "...", "class": "xxx"}]
        return []

    def get_questions(
        self,
        course_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        # TODO: POST /student/practice/getQuestions
        # courseId, classId, type(1=日常/2=章节/3=期末)
        return []

    def logout(self) -> None:
        self._token = ""
        self._user_id = ""
