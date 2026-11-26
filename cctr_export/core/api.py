"""CCTRCloud API 客户端（含完整分页校验与严格富文本解码）"""
from __future__ import annotations

import random
from typing import Callable, Optional
from urllib.parse import quote

from .http_utils import ResilientHttpSession, sniff_image_mime
from .integrity import decode_rich_content, has_visible_rich_content, is_choice_question
from .models import ChapterType, Option, Practice, Question, QuestionType
from .security import rsa_encrypt

BASE = "https://api.cctrcloud.net/mobile/index.php"


def _encode_params(pairs: list[tuple[str, object]]) -> str:
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in pairs)


class CCTRClient:
    def __init__(self, school_id: str, username: str, password: str):
        self.school_id = school_id
        self.username = username
        self.password = password
        self.key: str = ""
        self._client = ResilientHttpSession(timeout=60.0, prefer_direct=True)

    # ── 图像验证码 ────────────────────────────────
    def fetch_captcha(self) -> bytes:
        """获取图像验证码二进制数据并校验图片魔数。"""
        r = self._client.get(
            f"{BASE}?act=seccode&op=makecode&t={random.random()}",
            timeout=15.0,
            retries=2,
        )
        r.raise_for_status()
        if not sniff_image_mime(r.content):
            snippet = r.text[:120].replace("\n", " ")
            raise RuntimeError(f"验证码接口未返回有效图片（HTTP {r.status_code}）: {snippet}")
        return r.content

    # ── 登录 ──────────────────────────────────────
    def login(self, captcha: str = "") -> None:
        r = self._client.post(
            f"{BASE}?act=login&op=getschoolData",
            data=_encode_params([("number", self.school_id)]),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "getschoolData 失败"))
        real_school_id = d["datas"]["ID"]

        r = self._client.post(
            f"{BASE}?act=login",
            data=_encode_params([
                ("username", self.username),
                ("password", rsa_encrypt(self.password)),
                ("schoolid", real_school_id),
                ("client", "web"),
                ("captcha", captcha),
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

    # ── 题目列表（全量分页 + 完整性核对） ──────────
    def query_questions(
        self,
        practice: Practice,
        chapters: list[ChapterType] | None = None,
        question_types: list[QuestionType] | None = None,
        practiced: bool | None = None,
        page_count: int = 100,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Question]:
        """读取题目；默认同时拉取未练习(0)与已练习(1)，按平台章节/题型排序并严格去重核对总数。"""
        chapter_map: dict[str, str] = {}
        chapter_order: dict[str, int] = {}
        type_map: dict[str, str] = {}
        type_order: dict[str, int] = {}
        try:
            cat_chapters, cat_types = self.get_chapter_and_question_type(practice)
            for idx, ch in enumerate(cat_chapters):
                chapter_map[str(ch.id)] = ch.name or "未分类章节"
                chapter_order[str(ch.id)] = idx
            for idx, qt in enumerate(cat_types):
                tid = str(qt.question_type_id or qt.id)
                type_map[tid] = qt.name
                type_order[tid] = idx
        except Exception:
            pass

        practice_types = [1] if practiced is True else ([0] if practiced is False else [0, 1])
        raw_items: list[dict] = []
        seen_raw_ids: set[str] = set()
        observed_reported_count: Optional[int] = None

        for pt in practice_types:
            first_raw, split, reported_count = self._fetch_question_page_raw(
                practice, 1, page_count, chapters, question_types, pt, id_param=""
            )
            if reported_count is not None and observed_reported_count is None:
                observed_reported_count = reported_count

            # 平台对“未练习/已练习”任一状态均返回总题数 reported_count；若当前状态 list 与 split 均为空，说明该状态下本就无题
            if not first_raw and not split:
                continue

            bucket: list[dict] = list(first_raw)
            expected_bucket_count: Optional[int] = None
            if split:
                split_counts = [len([x for x in str(s).split(",") if x.strip()]) for s in split if str(s).strip()]
                if split_counts:
                    expected_bucket_count = sum(split_counts)
                if len(split) > 1 and expected_bucket_count and len(first_raw) < expected_bucket_count and len(split) < 2:
                    raise RuntimeError(f"平台未提供完整分页游标（{len(first_raw)}/{expected_bucket_count}），无法确认题目完整")
            elif len(practice_types) == 1 and reported_count is not None and len(first_raw) < reported_count:
                raise RuntimeError(f"平台未提供完整分页游标（{len(first_raw)}/{reported_count}），无法确认题目完整")

            for idx, sid in enumerate(split[1:], start=2):
                if not sid:
                    raise RuntimeError(f"第 {idx} 页分页游标无效，无法确认题目完整")
                page_raw, _, _ = self._fetch_question_page_raw(
                    practice, idx, page_count, chapters, question_types, pt, id_param=str(sid)
                )
                if not page_raw:
                    raise RuntimeError(f"第 {idx} 页返回为空，无法确认题目完整")
                bucket.extend(page_raw)

            bucket_ids: set[str] = set()
            for item in bucket:
                qid = str(item.get("questionid") or "").strip()
                if not qid or qid in bucket_ids:
                    raise RuntimeError(f"题目 ID 缺失或同状态页内重复：{qid or '(空)'}")
                bucket_ids.add(qid)

            if expected_bucket_count is not None and len(bucket) != expected_bucket_count:
                raise RuntimeError(f"分页题数不匹配：分片游标预期 {expected_bucket_count} 题，实际读取 {len(bucket)} 题")
            if len(practice_types) == 1 and reported_count is not None and len(bucket) < reported_count:
                raise RuntimeError(f"题数不匹配：平台报告 {reported_count} 题，实际读取 {len(bucket)} 题")

            for item in bucket:
                qid = str(item.get("questionid") or "").strip()
                if qid in seen_raw_ids:
                    raise RuntimeError(f"题目 {qid} 在不同练习状态中重复，无法确认内容完整")
                seen_raw_ids.add(qid)
                raw_items.append(item)

            if progress_callback:
                progress_callback(len(raw_items), practice.question_count or len(raw_items))

        if practiced is None:
            if observed_reported_count is not None and len(raw_items) < observed_reported_count:
                raise RuntimeError(
                    f"练习「{practice.practice_name}」题数不匹配：接口报告 {observed_reported_count}，实际获得 {len(raw_items)}"
                )
            if (
                not chapters
                and not question_types
                and practice.question_count is not None
                and len(raw_items) < practice.question_count
            ):
                raise RuntimeError(
                    f"练习「{practice.practice_name}」总题数不匹配：平台报告 {practice.question_count}，实际获得 {len(raw_items)}"
                )

        raw_items.sort(
            key=lambda q: (
                chapter_order.get(str(q.get("chapterid") or ""), len(chapter_order)),
                type_order.get(str(q.get("questiontypeid") or ""), len(type_order)),
            )
        )
        return [self._parse_question(q, practice, chapter_map, type_map) for q in raw_items]

    def _fetch_question_page_raw(
        self,
        practice: Practice,
        page_index: int,
        page_count: int,
        chapters: list[ChapterType] | None,
        question_types: list[QuestionType] | None,
        practice_type: int,
        id_param: str,
    ) -> tuple[list[dict], list[str], Optional[int]]:
        params = [
            ("key", self.key),
            ("courseid", practice.courseid),
            ("practiseid", practice.practise_id),
            ("studentpractiseid", practice.id),
            ("teacherid", practice.teacher_id),
            ("pagecount", page_count),
            ("pageindex", page_index),
            ("practisetype", practice_type),
            ("statenum", 0),
            ("id", id_param),
            ("list", "true"),
            ("studentpractisequestioncount", practice.question_count if practice.question_count is not None else 0),
        ]
        body = _encode_params(params)
        if chapters:
            body += "&" + _encode_params([("chapterid", ",".join(c.id for c in chapters))])
        if question_types:
            body += "&" + _encode_params([("questiontypeid", ",".join(q.question_type_id or q.id for q in question_types))])

        r = self._client.post(
            f"{BASE}?act=studentpracticeapi&op=getStudentPractiseQuestionList",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        d = r.json()
        if d["code"] != 200:
            raise RuntimeError(d["datas"].get("error", "获取题目失败"))
        datas = d.get("datas") or {}
        raw_list = datas.get("questionlist")
        if not isinstance(raw_list, list):
            raise RuntimeError("平台返回的 questionlist 格式不正确")
        split = datas.get("split") or []
        if not isinstance(split, list):
            raise RuntimeError("平台返回的 split 分页字段格式不正确")
        qcount_raw = datas.get("questioncount")
        reported_count = int(str(qcount_raw)) if str(qcount_raw).isdigit() else None
        return raw_list, [str(x) for x in split], reported_count

    def _parse_question(
        self,
        raw: dict,
        practice: Practice,
        chapter_map: dict[str, str],
        type_map: dict[str, str],
    ) -> Question:
        qid = str(raw.get("questionid", "")).strip()
        if not qid:
            raise RuntimeError("平台返回题目缺少 questionid")

        subqs = raw.get("subquestions")
        if isinstance(subqs, str):
            s_sub = subqs.strip()
            has_subqs = bool(s_sub and s_sub not in ("[]", "null", "None"))
        else:
            has_subqs = bool(subqs)
        if has_subqs:
            raise RuntimeError(f"题目 {qid} 包含子题结构，暂无法保证完整导出")

        subject_html = decode_rich_content(raw.get("subjecthtml_svg"))
        if not subject_html:
            raise RuntimeError(f"题目 {qid} 缺少题干内容")

        answer_html = decode_rich_content(raw.get("answerhtml_svg"))
        raw_analysis_html = decode_rich_content(raw.get("analysishtml_svg"))
        analysis_html = raw_analysis_html if has_visible_rich_content(raw_analysis_html) else ""

        qtype_id = str(raw.get("questiontypeid") or "").strip()
        qtype_name = type_map.get(qtype_id) or str(raw.get("questiontypename") or "").strip() or "未分类题型"
        choice = is_choice_question(qtype_name)

        options_raw = raw.get("options")
        if options_raw is not None and options_raw != "" and not isinstance(options_raw, list):
            raise RuntimeError(f"题目 {qid} 的选项格式不支持")
        has_options = isinstance(options_raw, list)
        options: list[Option] = []
        if has_options:
            if choice and len(options_raw) > 26:
                raise RuntimeError(f"题目 {qid} 的选项超过 26 个，无法确认字母标识")
            for opt in options_raw:
                opt_html = decode_rich_content(opt.get("questionoptionhtml_svg"))
                if not opt_html:
                    raise RuntimeError(f"题目 {qid} 存在空选项，无法确认题目完整")
                is_true = str(opt.get("istrue", "")) == "1"
                options.append(Option(is_true=is_true, html=opt_html))

        derived_answer = ""
        if choice and options:
            derived_answer = "、".join(chr(65 + idx) for idx, opt in enumerate(options) if opt.is_true)

        raw_ans = raw.get("answer")
        if raw_ans is not None and not isinstance(raw_ans, (str, int, float)):
            raise RuntimeError(f"题目 {qid} 的答案字段格式不支持")
        answer = answer_html or (str(raw_ans).strip() if raw_ans is not None else "") or derived_answer

        # 填空题等非选择题若将标准答案存放在 options 中，则转为答案区展示并清空 options，防止无答案版泄露
        if not answer and not choice and options:
            if len(options) == 1:
                answer = options[0].html
            else:
                answer = "<div>" + "".join(
                    f"<div><strong>（空 {idx + 1}）</strong>{opt.html}</div>" for idx, opt in enumerate(options)
                ) + "</div>"
            options = []
            has_options = False

        if not answer:
            raise RuntimeError(f"题目 {qid} 缺少答案，无法确认完整导出")

        chap_id = str(raw.get("chapterid") or "").strip()
        chap_name = chapter_map.get(chap_id) if chap_id and chap_id != "0" else "未分类章节"
        if not chap_name:
            chap_name = "未分类章节"

        return Question(
            id=f"{practice.id}:{qid}",
            question_type=qtype_name,
            subject_html=subject_html,
            answer=answer,
            has_options=has_options,
            options=options,
            subject_name=practice.lesson_name or practice.practice_name or "未分类学科",
            chapter_name=chap_name,
            analysis_html=analysis_html,
            is_choice=choice,
            chapter_id=chap_id,
            question_type_id=qtype_id,
        )

    def close(self):
        self._client.close()
