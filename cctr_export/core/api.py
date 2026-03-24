"""CCTRCloud API 客户端"""
from __future__ import annotations
import json
from urllib.parse import quote
from typing import Optional
import httpx
from .models import Practice, ChapterType, QuestionType, Question, Option
from .security import rsa_encrypt, decompress_gzip_base64

BASE = "https://api.cctrcloud.net/mobile/index.php"


def _encode_params(pairs: list[tuple[str, object]]) -> str:
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in pairs)


class CCTRClient:
    def __init__(self, school_id: str, username: str, password: str):
        self.school_id = school_id
        self.username = username
        self.password = password
        self.key: str = ""
        self._client = httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    # ── 登录 ──────────────────────────────────────
    def login(self) -> None:
        # 获取 schoolId
        r = self._client.post(
            f"{BASE}?act=login&op=getschoolData",
            data=_encode_params([("number", self.school_id)]),
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
                ("username", self.username),
                ("password", rsa_encrypt(self.password)),
                ("schoolid", real_school_id),
                ("client", "web"),
            ]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "登录失败"))
        self.key = d["datas"]["key"]

    # ── 练习列表 ──────────────────────────────────
    def get_practice_list(self) -> list[Practice]:
        r = self._client.post(
            f"{BASE}?act=studentpracticeapi&op=getPractiseCourseList",
            data=_encode_params([("key", self.key)]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "获取练习列表失败"))
        return [Practice.from_dict(x) for x in d["datas"]]

    # ── 章节与题型 ────────────────────────────────
    def get_chapter_and_question_type(self, practice: Practice) -> tuple[list[ChapterType], list[QuestionType]]:
        r = self._client.post(
            f"{BASE}?act=studentpracticeapi&op=getChapterListAndQuestionTypeList",
            data=_encode_params([
                ("key", self.key),
                ("courseid", practice.courseid),
                ("practiseid", practice.practise_id),
            ]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "获取章节题型失败"))
        datas = d["datas"]
        chapters = [ChapterType.from_dict(x) for x in datas.get("chapterList", [])]
        qtypes = [QuestionType.from_dict(x) for x in datas.get("questionTypeList", [])]
        return chapters, qtypes

    # ── 题目列表 ──────────────────────────────────
    def query_questions(
        self,
        practice: Practice,
        chapters: list[ChapterType] | None = None,
        question_types: list[QuestionType] | None = None,
        practiced: bool = False,
        page_count: int = 15,
    ) -> list[Question]:
        all_questions: list[Question] = []
        page_index = 1
        while True:
            qs, split = self._fetch_question_page(
                practice, page_index, page_count, chapters, question_types, practiced, id_param=""
            )
            all_questions.extend(qs)
            if not split or len(split) <= 1:
                break
            for sid in split[1:]:
                page_index += 1
                qs, _ = self._fetch_question_page(
                    practice, page_index, page_count, chapters, question_types, practiced, id_param=sid
                )
                all_questions.extend(qs)
        return all_questions

    def _fetch_question_page(
        self,
        practice: Practice,
        page_index: int,
        page_count: int,
        chapters: list[ChapterType] | None,
        question_types: list[QuestionType] | None,
        practiced: bool,
        id_param: str,
    ) -> tuple[list[Question], list[str]]:
        params = [
            ("key", self.key),
            ("courseid", practice.courseid),
            ("practiseid", practice.practise_id),
            ("studentpractiseid", practice.id),
            ("teacherid", practice.teacher_id),
            ("pagecount", page_count),
            ("pageindex", page_index),
            ("practisetype", 1 if practiced else 0),
            ("statenum", 0),
            ("id", id_param),
            ("list", "true"),
            ("studentpractisequestioncount", 53),
        ]
        body = _encode_params(params)
        if chapters:
            body += "&" + _encode_params([("chapterid", ",".join(c.id for c in chapters))])
        if question_types:
            body += "&" + _encode_params([("questiontypeid", ",".join(q.id for q in question_types))])

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
        subject_html = ""
        if raw.get("subjecthtml_svg"):
            try:
                subject_html = decompress_gzip_base64(raw["subjecthtml_svg"]).decode("utf-8")
            except Exception:
                subject_html = raw.get("subjecthtml_svg", "")

        answer_html = ""
        if raw.get("answerhtml_svg"):
            try:
                answer_html = decompress_gzip_base64(raw["answerhtml_svg"]).decode("utf-8")
            except Exception:
                answer_html = ""
        if not answer_html:
            answer_html = raw.get("answer", "")

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
                options.append(Option(is_true=(opt.get("istrue") == "1" or opt.get("istrue") == 1), html=html))

        return Question(
            id=str(raw.get("questionid", "")),
            question_type=raw.get("questiontypename", ""),
            subject_html=subject_html,
            answer=answer_html,
            has_options=has_options,
            options=options,
        )

    def close(self):
        self._client.close()
