"""通用题库格式双向转换中心与本地题库存储（.xlsx / .docx / .txt / .md / .json / .csv / Anki .tsv）"""
from __future__ import annotations

import csv
import html as html_lib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from .integrity import is_choice_question, validate_questions
from .models import ChapterType, Option, Practice, Question, QuestionType

_XML_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_TAG_BLOCK_RE = re.compile(r"<(?:/?(?:p|div|li|tr|h[1-6]|blockquote)|br\s*/?)>", re.I)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_ALL_TAGS_RE = re.compile(r"<[^>]+>")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_COL_LETTERS_RE = re.compile(r"^([A-Z]+)")

_HEADER_ALIASES: dict[str, str] = {
    "题干": "stem",
    "题目": "stem",
    "题目内容": "stem",
    "试题内容": "stem",
    "问题": "stem",
    "stem": "stem",
    "question": "stem",
    "title": "stem",
    "content": "stem",
    "front": "stem",
    "题型": "qtype",
    "题目类型": "qtype",
    "试题类型": "qtype",
    "类型": "qtype",
    "type": "qtype",
    "qtype": "qtype",
    "选项": "options_blob",
    "选择项": "options_blob",
    "供选项": "options_blob",
    "options": "options_blob",
    "答案": "answer",
    "正确答案": "answer",
    "标准答案": "answer",
    "参考答案": "answer",
    "answer": "answer",
    "back": "answer",
    "解析": "analysis",
    "题目解析": "analysis",
    "试题解析": "analysis",
    "答案解析": "analysis",
    "分析": "analysis",
    "analysis": "analysis",
    "explain": "analysis",
    "explanation": "analysis",
    "章节": "chapter",
    "章": "chapter",
    "chapter": "chapter",
    "学科": "subject",
    "科目": "subject",
    "课程": "subject",
    "课程名称": "subject",
    "source": "subject",
    "subject": "subject",
    "tags": "tags",
    "标签": "tags",
}

_SECTION_QTYPE_RE = re.compile(
    r"^(?:#{1,4}\s*|[一二三四五六七八九十]+[、.．]\s*|【|\()"
    r"(?:.*?(单选|多选|不定项|判断|填空|简答|计算|论述|问答|名词解释|综合).*?)$"
)
_Q_START_RE = re.compile(
    r"^(?:###\s*第\s*\d+\s*题(?:\s*[（(][^）)]*[）)])?\s*|(?:\[\s*(?P<tag1>[^\]\n]{1,12})\s*\]\s*|【\s*(?P<tag2>[^】\n]{1,12})\s*】\s*)?"
    r"(?:(?:第\s*\d+\s*题|\d+)\s*[.、．)\）]\s*|\(\d+\)\s*|（\d+）\s*))(?P<body>.*)$"
)
_INLINE_TYPE_RE = re.compile(r"[（(\[【](单选(?:题)?|多选(?:题)?|不定项(?:选择题)?|判断(?:题)?|填空(?:题)?|简答(?:题)?|计算(?:题)?|问答(?:题)?)[）)\]】]")
_SINGLE_OPT_RE = re.compile(r"^(?:[-*]\s*)?(?:\*\*|__)?([A-H])(?:\*\*|__)?\s*[.、．)\）:：]\s*(.+)$")
_INLINE_SPLIT_OPT_RE = re.compile(r"(?:^|\s{2,}|\t)([A-H])\s*[.、．)\）:：]\s*")
_ANS_LINE_RE = re.compile(r"^(?:>\s*)?(?:\*\*)?(?:【\s*(?:正确|标准|参考)?答案\s*】|(?:正确|标准|参考)?答案)(?:\*\*)?\s*[:：]?\s*(.*)$")
_ANA_LINE_RE = re.compile(r"^(?:>\s*)?(?:\*\*)?(?:【\s*(?:题目|试题|答案)?解析\s*】|(?:题目|试题|答案)?解析)(?:\*\*)?\s*[:：]?\s*(.*)$")


def _clean_xml_text(s: object) -> str:
    return _XML_CTRL_RE.sub("", str(s or ""))


def html_to_plain_text(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).replace("\r\n", "\n").replace("\r", "\n")
    has_img = bool(_IMG_TAG_RE.search(s))
    s = _TAG_BLOCK_RE.sub("\n", s)
    s = _IMG_TAG_RE.sub(" [图片] ", s)
    s = _ALL_TAGS_RE.sub("", s)
    s = html_lib.unescape(s).replace("\xa0", " ")
    lines = [ln.strip() for ln in s.split("\n")]
    joined = _MULTI_NL_RE.sub("\n\n", "\n".join(lines)).strip()
    if not joined and has_img:
        return "[图片]"
    return joined


def normalize_choice_answer_letters(ans: str) -> str:
    raw_plain = html_to_plain_text(ans)
    letters = sorted(set(re.findall(r"[A-Z]", raw_plain.upper())))
    return "".join(letters) if letters else raw_plain


def _col_index_to_letters(idx: int) -> str:
    res = ""
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(ord("A") + rem) + res
    return res


def _col_letters_to_index(ref: str) -> int:
    m = _COL_LETTERS_RE.match(ref.upper())
    if not m:
        return 0
    val = 0
    for ch in m.group(1):
        val = val * 26 + (ord(ch) - ord("A") + 1)
    return val - 1


def _strip_variant_answer_if_needed(q: Question, variant: str) -> tuple[list[Option], str, str]:
    if variant == "withoutAnswers":
        return [Option(is_true=False, html=o.html) for o in q.options], "", ""
    return q.options, q.answer, q.analysis_html


# ── Exporters ────────────────────────────────────────────────────────────────

def export_questions_to_xlsx(
    questions: list[Question],
    xlsx_path: str | Path,
    variant: str = "withAnswersRed",
    title: str = "题库",
) -> Path:
    items = validate_questions(questions)
    out_path = Path(xlsx_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    headers = ["题型", "题干", "选项A", "选项B", "选项C", "选项D", "选项E", "选项F", "选项G", "选项H", "答案", "解析", "章节", "学科"]
    rows: list[list[str]] = [headers]
    for q in items:
        opts, ans, ana = _strip_variant_answer_if_needed(q, variant)
        opt_cells = [html_to_plain_text(opts[i].html) if i < len(opts) else "" for i in range(8)]
        if variant == "withoutAnswers":
            ans_cell = ""
            ana_cell = ""
        else:
            if q.is_choice or is_choice_question(q.question_type):
                ans_cell = normalize_choice_answer_letters(ans)
                if not ans_cell and opts:
                    ans_cell = "".join(chr(ord("A") + i) for i, o in enumerate(opts) if o.is_true)
            else:
                ans_cell = html_to_plain_text(ans)
            ana_cell = html_to_plain_text(ana)
        rows.append([
            q.question_type or "未分类题型",
            html_to_plain_text(q.subject_html),
            *opt_cells,
            ans_cell,
            ana_cell,
            q.chapter_name or "未分类章节",
            q.subject_name or title or "未分类学科",
        ])

    row_xml_parts: list[str] = []
    for r_idx, row in enumerate(rows, 1):
        cells_xml: list[str] = []
        for c_idx, val in enumerate(row):
            clean = _clean_xml_text(val)
            if not clean:
                continue
            ref = f"{_col_index_to_letters(c_idx)}{r_idx}"
            cells_xml.append(
                f'<c r="{ref}" t="inlineStr"'
                + (' s="1"' if r_idx == 1 else "")
                + f'><is><t xml:space="preserve">{xml_escape(clean)}</t></is></c>'
            )
        row_xml_parts.append(f'<row r="{r_idx}">{"".join(cells_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols>'
        '<col min="1" max="1" width="12" customWidth="1"/>'
        '<col min="2" max="2" width="48" customWidth="1"/>'
        '<col min="3" max="10" width="22" customWidth="1"/>'
        '<col min="11" max="11" width="18" customWidth="1"/>'
        '<col min="12" max="12" width="36" customWidth="1"/>'
        '<col min="13" max="14" width="18" customWidth="1"/>'
        '</cols>'
        f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
        '</worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="题库导出" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font>'
        '<font><b/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF4F3EF"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '</styleSheet>'
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types.encode("utf-8"))
        zf.writestr("_rels/.rels", root_rels.encode("utf-8"))
        zf.writestr("xl/workbook.xml", workbook_xml.encode("utf-8"))
        zf.writestr("xl/_rels/workbook.rels", workbook_rels.encode("utf-8"))
        zf.writestr("xl/styles.xml", styles_xml.encode("utf-8"))
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml.encode("utf-8"))
    return out_path


def _anki_clean(s: str) -> str:
    return str(s or "").replace("\t", "    ").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def export_questions_to_anki_tsv(
    questions: list[Question],
    tsv_path: str | Path,
    title: str = "题库",
) -> Path:
    items = validate_questions(questions)
    out_path = Path(tsv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    safe_deck = str(title or "题库").replace("\t", " ").replace("\n", " ").strip() or "题库"
    lines = [
        "#separator:tab",
        "#html:true",
        f"#deck:{safe_deck}",
        "#tags column:4",
    ]
    for q in items:
        stem_html = q.subject_html if "<" in q.subject_html else html_lib.escape(q.subject_html)
        front_parts = [f"<b>[{html_lib.escape(q.question_type)}]</b> {stem_html}"]
        if q.has_options and q.options:
            for idx, opt in enumerate(q.options):
                lbl = f"{chr(ord('A') + idx)}. " if (q.is_choice or is_choice_question(q.question_type)) else ""
                opt_body = opt.html if "<" in opt.html else html_lib.escape(opt.html)
                front_parts.append(f"{lbl}{opt_body}")
        ans_html = q.answer if "<" in q.answer else html_lib.escape(q.answer)
        back_parts = [f"<b>答案：</b>{ans_html}"]
        if q.analysis_html.strip():
            ana_html = q.analysis_html if "<" in q.analysis_html else html_lib.escape(q.analysis_html)
            back_parts.append(f"<b>解析：</b>{ana_html}")
        source = f"{q.subject_name} / {q.chapter_name}"
        tags = " ".join(
            re.sub(r"\s+", "_", seg.strip())
            for seg in (q.subject_name, q.chapter_name, q.question_type)
            if seg and seg.strip()
        )
        lines.append("\t".join([
            _anki_clean("<br>".join(front_parts)),
            _anki_clean("<br>".join(back_parts)),
            _anki_clean(source),
            tags,
        ]))
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def export_questions_to_markdown(
    questions: list[Question],
    md_path: str | Path,
    variant: str = "withAnswersRed",
    title: str = "题库",
) -> Path:
    items = validate_questions(questions)
    out_path = Path(md_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = [f"# {title}\n"]
    prev_grp: Optional[tuple[str, str, str]] = None
    for idx, q in enumerate(items, 1):
        grp = (q.subject_name, q.chapter_name, q.question_type)
        if grp != prev_grp:
            parts.append(f"## {grp[0]} / {grp[1]} / {grp[2]}\n")
            prev_grp = grp
        opts, ans, ana = _strip_variant_answer_if_needed(q, variant)
        parts.append(f"### 第 {idx} 题（{q.question_type}）\n")
        parts.append(html_to_plain_text(q.subject_html) + "\n")
        if q.has_options and opts:
            for o_idx, opt in enumerate(opts):
                lbl = f"{chr(ord('A') + o_idx)}. " if (q.is_choice or is_choice_question(q.question_type)) else "- "
                text = html_to_plain_text(opt.html)
                if variant == "withAnswersRed" and opt.is_true:
                    parts.append(f"- **{lbl}{text}** ✓")
                else:
                    parts.append(f"- {lbl}{text}")
            parts.append("")
        if variant != "withoutAnswers":
            parts.append(f"> **答案**：{html_to_plain_text(ans)}")
            ana_txt = html_to_plain_text(ana)
            if ana_txt:
                parts.append(f"> **解析**：{ana_txt}")
            parts.append("")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return out_path


def export_questions_to_json(
    questions: list[Question],
    json_path: str | Path,
    variant: str = "withAnswersRed",
    title: str = "题库",
) -> Path:
    items = validate_questions(questions)
    out_path = Path(json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = []
    for q in items:
        opts, ans, ana = _strip_variant_answer_if_needed(q, variant)
        serialized.append({
            "id": q.id,
            "question_type": q.question_type,
            "subject_html": q.subject_html,
            "answer": ans,
            "has_options": q.has_options,
            "options": [{"is_true": o.is_true, "html": o.html} for o in opts],
            "subject_name": q.subject_name,
            "chapter_name": q.chapter_name,
            "analysis_html": ana,
            "is_choice": q.is_choice,
        })
    payload = {
        "version": 1,
        "title": title,
        "variant": variant,
        "questionCount": len(items),
        "questions": serialized,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ── Importers ────────────────────────────────────────────────────────────────

def _guess_question_type(raw_type: str, has_options: bool, ans: str, stem: str) -> str:
    t = (raw_type or "").strip()
    if t:
        return t
    if has_options:
        letters = re.findall(r"[A-H]", ans.upper())
        return "多选题" if len(set(letters)) > 1 else "单选题"
    if ans.strip() in ("对", "错", "正确", "错误", "√", "×", "T", "F", "True", "False"):
        return "判断题"
    if "___" in stem or "（）" in stem or "(  )" in stem or "（  ）" in stem:
        return "填空题"
    return "简答题"


def _mark_choice_options(options: list[Option], ans: str, choice: bool) -> list[Option]:
    if not choice or not options:
        return options
    letters = set(re.findall(r"[A-Z]", html_to_plain_text(ans).upper()))
    if not letters and not any(o.is_true for o in options):
        return options
    out: list[Option] = []
    for idx, opt in enumerate(options):
        lbl = chr(ord("A") + idx)
        out.append(Option(is_true=bool(opt.is_true or (lbl in letters)), html=opt.html))
    return out


def _build_imported_question(
    idx: int,
    stem: str,
    raw_type: str,
    option_texts: list[str],
    ans: str,
    analysis: str = "",
    subject_name: str = "导入题库",
    chapter_name: str = "全部题目",
    option_flags: Optional[list[bool]] = None,
    qid: Optional[str] = None,
) -> Optional[Question]:
    clean_stem = (stem or "").strip()
    if not clean_stem:
        return None
    opts: list[Option] = []
    for o_idx, txt in enumerate(option_texts):
        t = (txt or "").strip()
        if not t:
            continue
        flag = option_flags[o_idx] if option_flags and o_idx < len(option_flags) else False
        opts.append(Option(is_true=flag, html=t))

    clean_ans = (ans or "").strip()
    if not clean_ans and opts and any(o.is_true for o in opts):
        clean_ans = "、".join(chr(ord("A") + i) for i, o in enumerate(opts) if o.is_true)

    qtype = _guess_question_type(raw_type, bool(opts), clean_ans, clean_stem)
    choice = is_choice_question(qtype) or (bool(opts) and qtype in ("单选题", "多选题", "不定项选择题"))
    opts = _mark_choice_options(opts, clean_ans, choice)
    if not clean_ans:
        clean_ans = "略（原题未附答案）"

    return Question(
        id=qid or f"import:{idx}",
        question_type=qtype,
        subject_html=clean_stem,
        answer=clean_ans,
        has_options=bool(opts),
        options=opts,
        subject_name=(subject_name or "导入题库").strip() or "导入题库",
        chapter_name=(chapter_name or "全部题目").strip() or "全部题目",
        analysis_html=(analysis or "").strip(),
        is_choice=choice,
    )


def _split_option_blob(blob: str) -> list[str]:
    text = (blob or "").strip()
    if not text:
        return []
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", text) if ln.strip()]
    if len(lines) > 1:
        cleaned = []
        for ln in lines:
            m = _SINGLE_OPT_RE.match(ln)
            cleaned.append(m.group(2).strip() if m else ln)
        return cleaned
    parts = [p.strip() for p in re.split(r"\s*\|\|\s*|\^\^", text) if p.strip()]
    if len(parts) > 1:
        return parts
    # e.g. A. xxx  B. yyy  C. zzz
    inline = re.split(r"\s+(?=[A-H][.、．)\）:：])", text)
    if len(inline) > 1:
        return [_SINGLE_OPT_RE.match(p).group(2).strip() if _SINGLE_OPT_RE.match(p) else p for p in inline]
    return [text]


def _rows_to_questions(rows: list[list[str]], title: str) -> list[Question]:
    if not rows:
        return []
    header = [str(c or "").strip() for c in rows[0]]
    col_map: dict[str, int] = {}
    option_cols: list[tuple[str, int]] = []

    for idx, raw_col in enumerate(header):
        norm = re.sub(r"[\s_\-*（）()]+", "", raw_col).lower()
        opt_m = re.match(r"^(?:选项|option|choice)?([a-z])$", norm)
        if opt_m and norm not in _HEADER_ALIASES:
            option_cols.append((opt_m.group(1).upper(), idx))
            continue
        mapped = _HEADER_ALIASES.get(raw_col.strip()) or _HEADER_ALIASES.get(norm)
        if mapped and mapped not in col_map:
            col_map[mapped] = idx

    option_cols.sort(key=lambda x: x[0])

    # 若无明显表头，按常见默认列序：题型/题干/选项A..D/答案/解析 或 题干/A..D/答案
    data_start = 1 if ("stem" in col_map or "answer" in col_map or option_cols) else 0
    if data_start == 0:
        col_map = {"qtype": 0, "stem": 1, "answer": 6, "analysis": 7}
        option_cols = [("A", 2), ("B", 3), ("C", 4), ("D", 5)]

    out: list[Question] = []
    for r_i, row in enumerate(rows[data_start:], 1):
        def _cell(key: str) -> str:
            ci = col_map.get(key)
            return row[ci].strip() if ci is not None and ci < len(row) and row[ci] else ""

        stem = _cell("stem")
        ans = _cell("answer")
        if not stem and not ans:
            continue
        opts: list[str] = []
        for _, ci in option_cols:
            if ci < len(row) and row[ci] and row[ci].strip():
                opts.append(row[ci].strip())
        if not opts and "options_blob" in col_map:
            opts = _split_option_blob(_cell("options_blob"))

        q = _build_imported_question(
            idx=len(out) + 1,
            stem=stem,
            raw_type=_cell("qtype"),
            option_texts=opts,
            ans=ans,
            analysis=_cell("analysis"),
            subject_name=_cell("subject") or title,
            chapter_name=_cell("chapter") or "导入章节",
        )
        if q:
            out.append(q)
    return out


def import_xlsx_bytes(raw_bytes: bytes, title: str) -> list[Question]:
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
        names = set(zf.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root:
                texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                shared_strings.append("".join(texts))

        sheet_names = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        if not sheet_names:
            return []
        ws_root = ET.fromstring(zf.read(sheet_names[0]))
        rows: list[list[str]] = []
        for row_el in ws_root.iter():
            if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                continue
            row_cells: dict[int, str] = {}
            max_col = -1
            col_cursor = 0
            for c_el in row_el:
                if not (c_el.tag.endswith("}c") or c_el.tag == "c"):
                    continue
                ref = c_el.attrib.get("r", "")
                c_idx = _col_letters_to_index(ref) if ref else col_cursor
                col_cursor = c_idx + 1
                max_col = max(max_col, c_idx)
                c_type = c_el.attrib.get("t", "")
                val_text = ""
                if c_type == "inlineStr":
                    val_text = "".join(t.text or "" for t in c_el.iter() if t.tag.endswith("}t") or t.tag == "t")
                else:
                    v_el = next((ch for ch in c_el if ch.tag.endswith("}v") or ch.tag == "v"), None)
                    raw_v = (v_el.text or "") if v_el is not None else ""
                    if c_type == "s" and raw_v.isdigit():
                        s_idx = int(raw_v)
                        val_text = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                    else:
                        val_text = raw_v
                row_cells[c_idx] = val_text
            if max_col >= 0:
                rows.append([row_cells.get(i, "") for i in range(max_col + 1)])
    return _rows_to_questions(rows, title)


def _docx_bytes_to_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return ""
        root = ET.fromstring(zf.read("word/document.xml"))
    lines: list[str] = []
    for p_el in root.iter():
        if not (p_el.tag.endswith("}p") or p_el.tag == "p"):
            continue
        buf: list[str] = []
        for node in p_el.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t" and node.text:
                buf.append(node.text)
            elif tag == "tab":
                buf.append("\t")
            elif tag in ("br", "cr"):
                buf.append("\n")
        txt = "".join(buf).strip()
        if txt:
            lines.append(txt)
    return "\n".join(lines)


def parse_structured_text_questions(text: str, title: str = "文档题库") -> list[Question]:
    lines = [ln.rstrip() for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    out: list[Question] = []
    current_chapter = "全部题目"
    current_section_type = ""

    cur_stem: list[str] = []
    cur_type = ""
    cur_opts: list[str] = []
    cur_flags: list[bool] = []
    cur_ans: list[str] = []
    cur_ana: list[str] = []
    mode = ""  # "stem" | "opt" | "ans" | "ana"

    def flush():
        nonlocal cur_stem, cur_type, cur_opts, cur_flags, cur_ans, cur_ana, mode
        stem_str = "\n".join(x for x in cur_stem if x).strip()
        ans_str = "\n".join(x for x in cur_ans if x).strip()
        ana_str = "\n".join(x for x in cur_ana if x).strip()
        q = _build_imported_question(
            idx=len(out) + 1,
            stem=stem_str,
            raw_type=cur_type or current_section_type,
            option_texts=cur_opts,
            ans=ans_str,
            analysis=ana_str,
            subject_name=title,
            chapter_name=current_chapter,
            option_flags=cur_flags,
        )
        if q:
            out.append(q)
        cur_stem, cur_type, cur_opts, cur_flags, cur_ans, cur_ana, mode = [], "", [], [], [], [], ""

    for raw_ln in lines:
        ln = raw_ln.strip()
        if not ln:
            continue

        # Markdown / 章节大标题
        if ln.startswith("## "):
            flush()
            heading = ln[3:].strip()
            parts = [p.strip() for p in heading.split("/") if p.strip()]
            if len(parts) >= 2:
                current_chapter = parts[1]
            if len(parts) >= 3:
                current_section_type = parts[2]
            continue
        if ln.startswith("# ") and not out and not cur_stem:
            continue

        sec_m = _SECTION_QTYPE_RE.match(ln)
        if sec_m and len(ln) <= 32 and not _Q_START_RE.match(ln):
            flush()
            current_section_type = sec_m.group(1) + ("题" if not sec_m.group(1).endswith("题") else "")
            continue

        ans_m = _ANS_LINE_RE.match(ln)
        if ans_m and (cur_stem or cur_opts):
            mode = "ans"
            cur_ans.append(ans_m.group(1).strip())
            continue

        ana_m = _ANA_LINE_RE.match(ln)
        if ana_m and (cur_stem or cur_ans):
            mode = "ana"
            cur_ana.append(ana_m.group(1).strip())
            continue

        # 选项行（含单行多选项拆解）
        opt_m = _SINGLE_OPT_RE.match(ln)
        if opt_m and (cur_stem or cur_opts):
            mode = "opt"
            # 检查是否一行里有 A. xxx  B. yyy
            chunks = re.split(r"\s{2,}(?=[A-H][.、．)\）:：])|\t+(?=[A-H][.、．)\）:：])", ln)
            for ch in chunks:
                ch_s = ch.strip()
                is_marked = ch_s.endswith("✓") or ("**" in ch_s and ch_s.startswith("- **"))
                ch_clean = ch_s.rstrip("✓").strip()
                if ch_clean.startswith("**") and ch_clean.endswith("**") and len(ch_clean) > 4:
                    ch_clean = ch_clean[2:-2].strip()
                    is_marked = True
                sm = _SINGLE_OPT_RE.match(ch_clean)
                cur_opts.append((sm.group(2) if sm else ch_clean).strip())
                cur_flags.append(is_marked)
            continue

        q_m = _Q_START_RE.match(ln)
        if q_m:
            # 防止把选项或答案中“1.”的序号误判为新题：仅当当前不在解析/选项内部，或前面已经有答案，或新行显著像题干
            if cur_stem and (cur_opts or cur_ans or cur_ana or mode in ("ans", "ana")):
                flush()
            elif cur_stem and not cur_opts and not cur_ans:
                # 当前题刚读完题干还没有选项和答案，如果是下一题无选项填空/简答也应当切题
                flush()
            body = q_m.group("body").strip()
            tag = (q_m.group("tag1") or q_m.group("tag2") or "").strip()
            inline_t = _INLINE_TYPE_RE.search(body)
            if not tag and inline_t:
                tag = inline_t.group(1)
                body = _INLINE_TYPE_RE.sub("", body, count=1).strip()
            # 提取同行末尾【答案：X】
            inline_ans = re.search(r"[（(\[【](?:答案|正确答案)\s*[:：]\s*([^）)\]】]+)[）)\]】]\s*$", body)
            if inline_ans:
                cur_ans.append(inline_ans.group(1).strip())
                body = body[:inline_ans.start()].strip()
            cur_type = tag
            cur_stem.append(body or ln)
            mode = "stem"
            continue

        # 续行追加
        if mode == "ans":
            cur_ans.append(ln)
        elif mode == "ana":
            cur_ana.append(ln)
        elif mode == "opt" and cur_opts:
            cur_opts[-1] = (cur_opts[-1] + "\n" + ln).strip()
        else:
            cur_stem.append(ln)
            mode = "stem"

    flush()
    return out


def parse_json_questions(raw_json: str, title: str = "JSON题库") -> tuple[str, list[Question]]:
    data = json.loads(raw_json)
    doc_title = title
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        doc_title = str(data.get("title") or data.get("name") or title).strip() or title
        if isinstance(data.get("questions"), list):
            items = data["questions"]
        elif isinstance(data.get("data"), dict):
            d = data["data"]
            doc_title = str(d.get("name") or d.get("title") or doc_title).strip() or doc_title
            if isinstance(d.get("problems"), list):
                items = d["problems"]
            elif isinstance(d.get("questions"), list):
                items = d["questions"]
        elif isinstance(data.get("problems"), list):
            items = data["problems"]
        elif isinstance(data.get("items"), list):
            items = data["items"]
        elif isinstance(data.get("data"), list):
            items = data["data"]

    out: list[Question] = []
    for idx, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        # 1. 原生格式快速识别
        if "subject_html" in it:
            raw_opts = it.get("options") or []
            opts = [
                Option(is_true=bool(o.get("is_true")), html=str(o.get("html") or ""))
                for o in raw_opts
                if isinstance(o, dict) and str(o.get("html") or "").strip()
            ]
            qtype = str(it.get("question_type") or "未分类题型")
            ans = str(it.get("answer") or "").strip() or "略（原题未附答案）"
            out.append(
                Question(
                    id=str(it.get("id") or f"json:{idx}"),
                    question_type=qtype,
                    subject_html=str(it.get("subject_html") or ""),
                    answer=ans,
                    has_options=bool(it.get("has_options", bool(opts))),
                    options=opts,
                    subject_name=str(it.get("subject_name") or doc_title),
                    chapter_name=str(it.get("chapter_name") or "全部题目"),
                    analysis_html=str(it.get("analysis_html") or ""),
                    is_choice=bool(it.get("is_choice", is_choice_question(qtype))),
                )
            )
            continue

        # 2. chaoxing-question-exporter / Yuketang / 通用格式
        stem = str(
            it.get("Body") or it.get("body") or it.get("question") or it.get("stem")
            or it.get("title") or it.get("content") or ""
        ).strip()
        raw_type = str(it.get("TypeText") or it.get("typeText") or it.get("questionType") or it.get("qtype") or it.get("type") or "")
        # 雨课堂数字题型映射
        if raw_type in ("0", "1", "2", "3", "4", "5", "6"):
            raw_type = {
                "0": "单选题", "1": "单选题", "2": "多选题",
                "3": "多选题", "4": "判断题", "5": "填空题", "6": "简答题",
            }.get(raw_type, raw_type)

        raw_opts = it.get("Options") or it.get("options") or it.get("choices") or []
        opt_texts: list[str] = []
        opt_flags: list[bool] = []
        if isinstance(raw_opts, dict):
            for k in sorted(raw_opts.keys()):
                opt_texts.append(str(raw_opts[k]))
                opt_flags.append(False)
        elif isinstance(raw_opts, list):
            for o in raw_opts:
                if isinstance(o, dict):
                    txt = str(o.get("value") or o.get("name") or o.get("text") or o.get("html") or o.get("content") or "").strip()
                    flag = bool(o.get("isCorrect") or o.get("is_true") or o.get("isAnswer") or o.get("correct"))
                    if txt:
                        opt_texts.append(txt)
                        opt_flags.append(flag)
                elif o is not None and str(o).strip():
                    opt_texts.append(str(o).strip())
                    opt_flags.append(False)

        raw_ans = it.get("Answer") if it.get("Answer") is not None else (
            it.get("answer") if it.get("answer") is not None else (it.get("correctAnswer") or it.get("rightAnswer") or "")
        )
        if isinstance(raw_ans, list):
            ans_str = "、".join(str(x) for x in raw_ans)
        elif isinstance(raw_ans, dict):
            ans_str = "；".join(f"{k}: {v}" for k, v in raw_ans.items())
        else:
            ans_str = str(raw_ans or "")

        ana = str(it.get("Remark") or it.get("analysis") or it.get("explain") or it.get("explanation") or "")
        chap = str(it.get("chapter") or it.get("chapterName") or "导入章节")
        subj = str(it.get("subject") or it.get("courseName") or doc_title)

        q = _build_imported_question(
            idx=len(out) + 1,
            stem=stem,
            raw_type=raw_type,
            option_texts=opt_texts,
            ans=ans_str,
            analysis=ana,
            subject_name=subj,
            chapter_name=chap,
            option_flags=opt_flags,
            qid=str(it.get("id") or it.get("problem_id") or f"json:{idx}"),
        )
        if q:
            out.append(q)
    return doc_title, out


def _import_csv_or_tsv(text: str, title: str, delimiter: str) -> list[Question]:
    lines = text.splitlines()
    filtered = [ln for ln in lines if not ln.startswith("#")]
    if not filtered:
        return []
    reader = csv.reader(filtered, delimiter=delimiter)
    rows = [[str(c) for c in row] for row in reader if any(str(c).strip() for c in row)]
    if not rows:
        return []
    # 检查是否为 Anki 导出的 Front/Back 格式
    if lines[0].startswith("#separator:tab") and len(rows[0]) >= 2:
        out: list[Question] = []
        for idx, r in enumerate(rows, 1):
            front = r[0] if len(r) > 0 else ""
            back = r[1] if len(r) > 1 else ""
            source = r[2] if len(r) > 2 else title
            if not front.strip():
                continue
            q = _build_imported_question(
                idx=idx,
                stem=front,
                raw_type="卡片",
                option_texts=[],
                ans=back,
                subject_name=source or title,
                chapter_name="Anki 卡片",
            )
            if q:
                out.append(q)
        return out
    return _rows_to_questions(rows, title)


def import_questions_from_file(path: str | Path, default_subject: str = "") -> tuple[str, list[Question]]:
    p = Path(path)
    title = default_subject or p.stem or "导入题库"
    ext = p.suffix.lower()
    if ext == ".xlsx":
        qs = import_xlsx_bytes(p.read_bytes(), title)
    elif ext == ".docx":
        text = _docx_bytes_to_text(p.read_bytes())
        qs = parse_structured_text_questions(text, title)
    elif ext == ".json":
        title, qs = parse_json_questions(p.read_text(encoding="utf-8-sig"), title)
    elif ext in (".csv", ".tsv"):
        raw = p.read_text(encoding="utf-8-sig")
        delim = "\t" if ext == ".tsv" or raw.startswith("#separator:tab") else ","
        qs = _import_csv_or_tsv(raw, title, delim)
    elif ext in (".txt", ".md", ".markdown"):
        qs = parse_structured_text_questions(p.read_text(encoding="utf-8-sig"), title)
    else:
        raise ValueError(f"暂不支持的文件格式：{ext}（支持 .xlsx / .docx / .txt / .md / .json / .csv / .tsv）")

    if not qs:
        raise ValueError(f"未能从「{p.name}」中识别到有效题目，请检查格式模板")
    validate_questions(qs)
    return title, qs


# ── 本地扩展题库存储（供学习通 / 雨课堂 / 本地导入接入 TaskEngine） ────────────

def _banks_dir() -> Path:
    d = Path.home() / ".cctr_export" / "banks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_local_bank(title: str, source_label: str, questions: list[Question], bank_id: Optional[str] = None) -> Practice:
    items = validate_questions(questions)
    bid = bank_id or uuid.uuid4().hex[:12]
    clean_title = (title or "未命名题库").strip() or "未命名题库"
    clean_source = (source_label or "多平台题库").strip() or "多平台题库"
    target = _banks_dir() / f"{bid}.json"
    export_questions_to_json(items, target, variant="withAnswersRed", title=clean_title)
    numeric_id = -(abs(hash(bid)) % 900_000_000 + 1000)
    return Practice(
        id=numeric_id,
        courseid="__local_bank__",
        practise_id=bid,
        teacher_id=clean_source,
        lesson_name=clean_source,
        practice_name=clean_title,
        teacher_name=clean_source,
        finish_time="",
        question_count=len(items),
    )


def load_local_bank_questions(
    bank_id: str,
    chapters: Optional[list[ChapterType]] = None,
    question_types: Optional[list[QuestionType]] = None,
) -> list[Question]:
    target = _banks_dir() / f"{bank_id}.json"
    if not target.exists():
        raise FileNotFoundError(f"本地题库缓存不存在或已清理：{bank_id}")
    _, items = parse_json_questions(target.read_text(encoding="utf-8"), bank_id)
    if chapters:
        allowed_ch = {c.name or c.id for c in chapters}
        items = [q for q in items if q.chapter_name in allowed_ch]
    if question_types:
        allowed_qt = {qt.name or qt.id for qt in question_types}
        items = [q for q in items if q.question_type in allowed_qt]
    return items


def get_local_bank_filters(bank_id: str) -> tuple[list[ChapterType], list[QuestionType]]:
    items = load_local_bank_questions(bank_id)
    ch_seen: list[str] = []
    qt_seen: list[str] = []
    for q in items:
        if q.chapter_name and q.chapter_name not in ch_seen:
            ch_seen.append(q.chapter_name)
        if q.question_type and q.question_type not in qt_seen:
            qt_seen.append(q.question_type)
    return (
        [ChapterType(id=c, course_id="__local_bank__", name=c) for c in ch_seen],
        [QuestionType(question_type_id=qt, id=qt, name=qt) for qt in qt_seen],
    )
