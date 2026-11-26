import base64
import io
import json
import struct
import zipfile
from pathlib import Path

import pytest

from cctr_export.core import database as db
from cctr_export.core.captcha_ocr import is_ocr_available
from cctr_export.core.formats import (
    export_questions_to_anki_tsv,
    export_questions_to_json,
    export_questions_to_markdown,
    export_questions_to_xlsx,
    import_questions_from_file,
    parse_json_questions,
    parse_structured_text_questions,
    save_local_bank,
)
from cctr_export.core.models import Option, Practice, Question
from cctr_export.core.tasks import engine
from cctr_export.core.web_capture import (
    apply_glyph_map_to_html,
    build_questions_from_capture,
    parse_ttf_cmap_codepoints,
)


def _sample_questions() -> list[Question]:
    return [
        Question(
            id="t:1",
            question_type="单选题",
            subject_html="<p>香农公式计算信道容量时带宽与什么成正比？</p>",
            answer="A",
            has_options=True,
            options=[
                Option(is_true=True, html="传输速率能力（线性相关）"),
                Option(is_true=False, html="载波相位噪声"),
            ],
            subject_name="通信原理",
            chapter_name="第一章",
            analysis_html="<p>C = B log2(1 + S/N)</p>",
            is_choice=True,
        ),
        Question(
            id="t:2",
            question_type="多选题",
            subject_html="<p>下列属于数字调制方式的有？</p>",
            answer="A、C",
            has_options=True,
            options=[
                Option(is_true=True, html="ASK"),
                Option(is_true=False, html="AM"),
                Option(is_true=True, html="PSK"),
            ],
            subject_name="通信原理",
            chapter_name="第三章",
            analysis_html="",
            is_choice=True,
        ),
        Question(
            id="t:3",
            question_type="填空题",
            subject_html="<p>奈奎斯特第一准则要求码间串扰为___。</p>",
            answer="0",
            has_options=False,
            options=[],
            subject_name="通信原理",
            chapter_name="第四章",
            analysis_html="无码间串扰条件",
            is_choice=False,
        ),
    ]


def test_xlsx_export_and_import_roundtrip(tmp_path: Path):
    qs = _sample_questions()
    xlsx_path = tmp_path / "通信原理题库.xlsx"
    export_questions_to_xlsx(qs, xlsx_path, variant="withAnswersRed", title="通信原理")
    assert xlsx_path.exists()

    title, imported = import_questions_from_file(xlsx_path)
    assert title == "通信原理题库"
    assert len(imported) == 3
    assert imported[0].question_type == "单选题"
    assert imported[0].options[0].is_true is True
    assert imported[1].answer == "AC"
    assert imported[1].options[0].is_true is True and imported[1].options[2].is_true is True
    assert imported[2].question_type == "填空题"
    assert imported[2].answer == "0"

    blank_xlsx = tmp_path / "blank.xlsx"
    export_questions_to_xlsx(qs, blank_xlsx, variant="withoutAnswers", title="空白卷")
    _, blank_imp = import_questions_from_file(blank_xlsx)
    assert blank_imp[0].answer == "略（原题未附答案）"


def test_docx_md_txt_anki_and_json_roundtrips(tmp_path: Path):
    qs = _sample_questions()

    # 1. Word .docx 导入（真实 OOXML word/document.xml）
    docx_path = tmp_path / "sample.docx"
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>一、单选题</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>1. HTTP 默认端口是多少？</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>A. 80</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>B. 443</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>答案：A</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>解析：HTTPS 才是 443</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
    _, docx_qs = import_questions_from_file(docx_path)
    assert len(docx_qs) == 1
    assert docx_qs[0].question_type == "单选题"
    assert docx_qs[0].options[0].is_true is True
    assert "443" in docx_qs[0].analysis_html

    # 2. Markdown 导出 -> 导入
    md_path = tmp_path / "notes.md"
    export_questions_to_markdown(qs, md_path, variant="withAnswersRed", title="通信原理讲义")
    _, md_qs = import_questions_from_file(md_path)
    assert len(md_qs) == 3
    assert md_qs[0].options[0].is_true is True

    # 3. Anki .tsv 导出 -> 导入
    tsv_path = tmp_path / "anki_cards.tsv"
    export_questions_to_anki_tsv(qs, tsv_path, title="通信原理卡片")
    raw_tsv = tsv_path.read_text(encoding="utf-8")
    assert "#separator:tab" in raw_tsv
    _, tsv_qs = import_questions_from_file(tsv_path)
    assert len(tsv_qs) == 3

    # 4. 原生 JSON 导出 -> 导入
    json_path = tmp_path / "native.json"
    export_questions_to_json(qs, json_path, variant="withAnswersRed", title="标准备份")
    jtitle, json_qs = import_questions_from_file(json_path)
    assert jtitle == "标准备份"
    assert len(json_qs) == 3


def test_chaoxing_and_yuketang_json_compatibility():
    cx_json = json.dumps({
        "title": "超星学习通第一章测验",
        "questions": [
            {
                "title": "计算机网络采用什么交换方式传输分组？",
                "type": "单选题",
                "options": ["电路交换", "分组交换"],
                "answer": "B",
                "analysis": "现代互联网核心基于分组交换",
            }
        ],
    }, ensure_ascii=False)
    t1, q1 = parse_json_questions(cx_json)
    assert t1 == "超星学习通第一章测验"
    assert len(q1) == 1 and q1[0].options[1].is_true is True

    ykt_json = json.dumps({
        "code": 0,
        "data": {
            "name": "雨课堂随堂小测",
            "problems": [
                {
                    "ProblemID": 8891,
                    "Type": 0,
                    "Body": "<p>TCP 握手需要几次？</p>",
                    "Options": [{"key": "A", "value": "两次"}, {"key": "B", "value": "三次"}],
                    "Answer": ["B"],
                    "Remark": "SYN -> SYN-ACK -> ACK",
                }
            ],
        },
    }, ensure_ascii=False)
    t2, q2 = parse_json_questions(ykt_json)
    assert t2 == "雨课堂随堂小测"
    assert len(q2) == 1 and q2[0].question_type == "单选题" and q2[0].options[1].is_true is True


def _build_minimal_cmap_format4_ttf(codepoints: list[int]) -> bytes:
    """构造仅含 cmap Format 4 subtable 的最小有效 SFNT/TTF 二进制用于单测。"""
    sorted_cps = sorted(set(codepoints)) + [0xFFFF]
    seg_count = len(sorted_cps)
    seg_count_x2 = seg_count * 2
    end_codes = b"".join(struct.pack(">H", cp) for cp in sorted_cps)
    start_codes = b"".join(struct.pack(">H", cp) for cp in sorted_cps)
    subtable_len = 14 + seg_count_x2 * 2 + 2
    subtable = struct.pack(">HHHHHHH", 4, subtable_len, 0, seg_count_x2, 0, 0, 0) + end_codes + b"\x00\x00" + start_codes
    cmap_header = struct.pack(">HH", 0, 1) + struct.pack(">HHI", 3, 1, 12) + subtable
    # SFNT offset table (12 bytes) + 1 table record (16 bytes) -> cmap starts at 28
    cmap_off = 28
    sfnt = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0) + b"cmap" + struct.pack(">III", 0, cmap_off, len(cmap_header))
    return sfnt + cmap_header


def test_ttf_cmap_parser_and_glyph_decryption_and_host_guard():
    ttf = _build_minimal_cmap_format4_ttf([0x4E2D, 0x6587, 0xE123])
    cps = parse_ttf_cmap_codepoints(ttf)
    assert {0x4E2D, 0x6587, 0xE123}.issubset(cps)

    # 验证标签外解密不会破坏 HTML img tag 与 data URI
    raw_html = '<p>\ue001\ue002</p><img src="https://p.ananas.chaoxing.com/star3/origin/a.png" />'
    dec = apply_glyph_map_to_html(raw_html, {"\ue001": "信", "\ue002": "号"})
    assert dec == '<p>信号</p><img src="https://p.ananas.chaoxing.com/star3/origin/a.png" />'

    # 验证端侧 ddddocr 还原渲染字体字形（若系统存在宋体且 ocr 可用）
    simsun = Path(r"C:\Windows\Fonts\simsun.ttc")
    secret_glyphs = []
    if is_ocr_available() and simsun.exists():
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(str(simsun), 42)
        for fake, real in [("\ue010", "通"), ("\ue011", "信")]:
            img = Image.new("RGB", (64, 64), "white")
            dr = ImageDraw.Draw(img)
            bb = dr.textbbox((0, 0), real, font=font)
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            dr.text(((64 - w) / 2 - bb[0], (64 - h) / 2 - bb[1]), real, fill="black", font=font)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            secret_glyphs.append({"char": fake, "pngBase64": base64.b64encode(buf.getvalue()).decode("ascii")})

    payload = {
        "ok": True,
        "title": "超星测试",
        "sourceLabel": "超星学习通",
        "items": [
            {
                "id": "cx:1",
                "questionType": "单选题",
                "stemHtml": '<p>\ue010\ue011原理基础</p><img src="https://p.ananas.chaoxing.com/demo.png">',
                "options": [{"isTrue": False, "html": "A. 选项一"}],
                "answerHtml": "A",
                "analysisHtml": "",
            }
        ],
        "secretGlyphs": secret_glyphs,
    }
    title, qs = build_questions_from_capture(payload)
    assert title == "超星测试"
    assert len(qs) == 1
    if secret_glyphs:
        assert "通信原理基础" in qs[0].subject_html
    assert "p.ananas.chaoxing.com" in qs[0].subject_html

    # 验证不受信任域名依然被拦截
    bad_payload = {
        "ok": True,
        "title": "bad",
        "items": [{"id": "1", "questionType": "单选题", "stemHtml": '<img src="https://evil.com/x.png">', "options": [], "answerHtml": "A"}],
    }
    with pytest.raises(ValueError, match="允许域"):
        build_questions_from_capture(bad_payload)


def test_task_engine_runs_local_bank_and_new_formats(tmp_path: Path, monkeypatch):
    fake_home = tmp_path / "home"
    out_dir = tmp_path / "exports"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr("cctr_export.core.tasks.get_export_dir", lambda: out_dir)
    db.init_db()

    practice = save_local_bank("跨平台导出测试", "学习通", _sample_questions())
    assert practice.courseid == "__local_bank__"

    for fmt, suffix in [
        (db.ExportType.XLSX, ".xlsx"),
        (db.ExportType.ANKI, ".tsv"),
        (db.ExportType.MD, ".md"),
        (db.ExportType.JSON, ".json"),
    ]:
        tid = db.add_task(
            "multi",
            "测试用户",
            "",
            fmt,
            [{"practice": practice.to_json(), "chapters": [], "question_types": [], "variant": "withAnswersRed"}],
        )
        engine._run(tid)
        rec = db.get_task(tid)
        assert rec is not None and rec.status == db.TaskStatus.SUCCESS
        assert rec.output_path.endswith(suffix)
        assert Path(rec.output_path).exists()
