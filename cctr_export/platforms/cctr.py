"""CCTRCloud 题库平台实现（迁移自 core/api.py）"""
from __future__ import annotations
from typing import Optional, Callable, TYPE_CHECKING
from .base import BasePlatform, Question, Option, QuestionTypeEnum, register_platform
from .security import rsa_encrypt, decompress_gzip_base64
from urllib.parse import quote
import httpx

if TYPE_CHECKING:
    from .base import Question as BaseQuestion

BASE = "https://api.cctrcloud.net/mobile/index.php"


def _encode_params(pairs) -> str:
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in pairs)


@register_platform("cctr")
class CCTRPlatform(BasePlatform):
    """CCTRCloud 题库平台"""

    platform_name = "cctr"

    def __init__(self):
        self.key: str = ""
        self._client = httpx.Client(
            timeout=60, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )

    # ── 登录 ──────────────────────────────────────

    def login(self, school_id: str, username: str, password: str) -> None:
        # 获取真实 schoolId
        r = self._client.post(
            f"{BASE}?act=login&op=getschoolData",
            data=_encode_params([("number", school_id)]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "getschoolData 失败"))

        real_school_id = d["datas"]["ID"]

        # RSA 加密登录
        r = self._client.post(
            f"{BASE}?act=login",
            data=_encode_params([
                ("username", username),
                ("password", rsa_encrypt(password)),
                ("schoolid", real_school_id),
                ("client", "web"),
            ]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "登录失败"))
        self.key = d["datas"]["key"]

    # ── 课程列表 ─────────────────────────────────

    def get_courses(self) -> list[dict]:
        r = self._client.post(
            f"{BASE}?act=studentpracticeapi&op=getPractiseCourseList",
            data=_encode_params([("key", self.key)]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "获取练习列表失败"))

        courses = []
        for item in d["datas"]:
            courses.append({
                "id": str(item.get("practiseid", "")),
                "courseid": str(item.get("courseid", "")),
                "name": item.get("practise_name", item.get("title", "")),
                "teacher_id": str(item.get("teacherid", "")),
                "type": "practice",
            })
        return courses

    # ── 题目列表 ─────────────────────────────────

    def get_questions(
        self,
        course_id: str,
        chapter_ids: Optional[list[str]] = None,
        question_type_ids: Optional[list[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        """
        Args:
            course_id:  格式 "practiseid|courseid|teacherid"（用 | 分隔）
            chapter_ids: 章节 ID 列表，None = 全部
            question_type_ids: 题型 ID 列表，None = 全部
        """
        parts = course_id.split("|")
        if len(parts) != 3:
            raise ValueError(f"course_id 格式应为 'practiseid|courseid|teacherid'，实际: {course_id}")

        practise_id, courseid, teacher_id = parts

        all_questions: list[Question] = []
        page_index = 1
        page_count = 15

        while True:
            qs, split = self._fetch_page(
                practise_id, courseid, teacher_id,
                page_index, page_count,
                chapter_ids, question_type_ids,
            )
            all_questions.extend(qs)

            if progress_callback:
                progress_callback(len(all_questions), 0)  # 0=未知总数

            if not split or len(split) <= 1:
                break
            for sid in split[1:]:
                page_index += 1
                qs, _ = self._fetch_page(
                    practise_id, courseid, teacher_id,
                    page_index, page_count,
                    chapter_ids, question_type_ids,
                    id_param=sid,
                )
                all_questions.extend(qs)

        return all_questions

    def _fetch_page(
        self,
        practise_id: str,
        courseid: str,
        teacher_id: str,
        page_index: int,
        page_count: int,
        chapter_ids: Optional[list[str]],
        question_type_ids: Optional[list[str]],
        id_param: str = "",
    ) -> tuple[list[Question], list[str]]:
        params = [
            ("key", self.key),
            ("courseid", courseid),
            ("practiseid", practise_id),
            ("studentpractiseid", practise_id),  # 复用 practiseid
            ("teacherid", teacher_id),
            ("pagecount", page_count),
            ("pageindex", page_index),
            ("practisetype", 0),
            ("statenum", 0),
            ("id", id_param),
            ("list", "true"),
            ("studentpractisequestioncount", 53),
        ]
        body = _encode_params(params)
        if chapter_ids:
            body += "&" + _encode_params([("chapterid", ",".join(chapter_ids))])
        if question_type_ids:
            body += "&" + _encode_params([("questiontypeid", ",".join(question_type_ids))])

        r = self._client.post(
            f"{BASE}?act=studentpracticeapi&op=getStudentPractiseQuestionList",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "获取题目失败"))

        datas = d["datas"]
        raw_list = datas.get("questionlist", [])
        split = datas.get("split", [])

        questions = [self._parse_question(q) for q in raw_list]
        return questions, split

    def _parse_question(self, raw: dict) -> Question:
        # 题目正文
        subject_html = ""
        if raw.get("subjecthtml_svg"):
            try:
                subject_html = decompress_gzip_base64(raw["subjecthtml_svg"]).decode("utf-8")
            except Exception:
                subject_html = raw.get("subjecthtml_svg", "")

        # 答案
        answer_html = ""
        if raw.get("answerhtml_svg"):
            try:
                answer_html = decompress_gzip_base64(raw["answerhtml_svg"]).decode("utf-8")
            except Exception:
                answer_html = ""
        if not answer_html:
            answer_html = raw.get("answer", "")

        # 选项
        options_raw = raw.get("options")
        has_options = isinstance(options_raw, list)
        options: list[Option] = []
        if has_options:
            for opt in options_raw:
                html = ""
                if opt.get("questionoptionhtml_svg"):
                    try:
                        html = decompress_gzip_base64(opt["questionoptionhtml_svg"]).decode("utf-8")
                    except Exception:
                        html = opt.get("questionoptionhtml_svg", "")
                options.append(Option(
                    label=opt.get("label", "?"),
                    html=html,
                    is_true=(opt.get("istrue") == "1" or opt.get("istrue") == 1),
                ))

        # 题型映射
        qtype_str = raw.get("questiontypename", "单选题")
        qtype_enum = self._map_question_type(qtype_str)

        return Question(
            platform=self.platform_name,
            external_id=str(raw.get("questionid", "")),
            question_type=qtype_str,
            question_type_enum=qtype_enum,
            subject_html=subject_html,
            answer_html=answer_html,
            has_options=has_options,
            options=options,
        )

    @staticmethod
    def _map_question_type(qtype_str: str) -> QuestionTypeEnum:
        mapping = {
            "单选题": QuestionTypeEnum.SINGLE,
            "多选题": QuestionTypeEnum.MULTIPLE,
            "判断题": QuestionTypeEnum.JUDGE,
            "填空题": QuestionTypeEnum.FILL,
            "简答题": QuestionTypeEnum.ESSAY,
            "论述题": QuestionTypeEnum.ESSAY,
        }
        return mapping.get(qtype_str, QuestionTypeEnum.SINGLE)

    def logout(self) -> None:
        self._client.close()
