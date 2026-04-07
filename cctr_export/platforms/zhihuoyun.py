"""职教云题库平台"""
from typing import Optional, Callable
from .base import BasePlatform, Question, QuestionTypeEnum, register_platform


@register_platform("zhihuoyun")
class ZhihuiYunPlatform(BasePlatform):
    """
    职教云（各省子平台，如江西职教云、浙江职教云等）
    架构与智慧职教类似，API 端点略有不同
    """
    platform_name = "zhihuoyun"

    # 各省职教云入口（可配置）
    BASE_URLS = {
        "jx": "https://www.jxve.cn",      # 江西
        "zj": "https://www.zjve.cn",       # 浙江
        "sd": "https://www.sdve.cn",       # 山东
        "default": "https://www.icve.com.cn",
    }

    def __init__(self, province: str = "default"):
        self._base_url = self.BASE_URLS.get(province, self.BASE_URLS["default"])
        self._token: str = ""

    def login(self, school_id: str, username: str, password: str) -> None:
        import httpx
        # TODO: POST {self._base_url}/portal/login
        # 职教云各省独立部署，统一走智慧职教底层架构
        self._token = ""

    def get_courses(self) -> list[dict]:
        # TODO: GET /portal/student/myCourse
        return []

    def get_questions(
        self,
        course_id: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        # TODO: 获取课后练习 + 章节测验
        return []

    def logout(self) -> None:
        self._token = ""
