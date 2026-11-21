"""数据模型"""
from __future__ import annotations
import dataclasses
import json
from typing import Optional


@dataclasses.dataclass
class Practice:
    id: int
    courseid: str
    practise_id: str
    teacher_id: str
    lesson_name: str
    practice_name: str
    teacher_name: str
    finish_time: str
    question_count: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> Practice:
        def _v(d, *keys):
            for k in keys:
                if k in d and d[k] is not None:
                    return str(d[k])
            return ""

        raw_qcount = _v(d, "questioncount", "questionCount", "question_count", "studentpractisequestioncount")
        qcount: Optional[int] = int(raw_qcount) if raw_qcount.isdigit() else None

        return cls(
            id=int(_v(d, "id", "ID") or "0"),
            courseid=_v(d, "courseid", "courseId", "course_id") or "0",
            practise_id=_v(d, "practiseid", "practiseId", "practise_id"),
            teacher_id=_v(d, "teacherid", "teacherId", "teacher_id"),
            lesson_name=_v(d, "lessonname", "lessonName", "lesson_name"),
            practice_name=_v(d, "practicename", "practiceName", "practice_name"),
            teacher_name=_v(d, "teachernumber", "teacherNumber", "teacher_number"),
            finish_time=_v(d, "finishtime", "finishTime", "finish_time"),
            question_count=qcount,
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, s: str) -> Practice:
        return cls.from_dict(json.loads(s))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclasses.dataclass
class ChapterType:
    id: str
    course_id: str
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> ChapterType:
        def _v(d, *keys):
            for k in keys:
                if k in d and d[k] is not None:
                    return str(d[k])
            return ""
        return cls(
            id=_v(d, "id", "ID") or "",
            course_id=_v(d, "courseid", "courseId", "course_id") or "",
            name=_v(d, "name", "chapterName", "chapter_name"),
        )

    def to_dict(self) -> dict:
        return {"id": self.id, "courseid": self.course_id, "name": self.name}

    def __hash__(self):
        return hash((self.id, self.course_id))

    def __eq__(self, other):
        return isinstance(other, ChapterType) and self.id == other.id and self.course_id == other.course_id


@dataclasses.dataclass
class QuestionType:
    question_type_id: str
    id: str
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> QuestionType:
        def _v(d, *keys):
            for k in keys:
                if k in d and d[k] is not None:
                    return str(d[k])
            return ""
        return cls(
            question_type_id=_v(d, "questiontypeid", "questionTypeId", "question_type_id"),
            id=_v(d, "id", "ID") or "",
            name=_v(d, "cname", "name", "questionTypeName"),
        )

    def to_dict(self) -> dict:
        return {"questiontypeid": self.question_type_id, "id": self.id, "cname": self.name}

    def __hash__(self):
        return hash((self.question_type_id, self.id))

    def __eq__(self, other):
        return isinstance(other, QuestionType) and self.question_type_id == other.question_type_id and self.id == other.id


@dataclasses.dataclass
class Option:
    is_true: bool
    html: str


@dataclasses.dataclass
class Question:
    id: str
    question_type: str
    subject_html: str
    answer: str
    has_options: bool
    options: list[Option]
    subject_name: str = "未分类学科"
    chapter_name: str = "未分类章节"
    analysis_html: str = ""
    is_choice: bool = False
    chapter_id: str = ""
    question_type_id: str = ""
