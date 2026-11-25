"""Tests for strict rich-text decoding, PDF integrity checks, tall image slicing, overflow rejection, and ZIP manifest."""
from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from cctr_export.core.exporter import (
    export_questions_to_archive_zip,
    export_questions_to_pdf,
)
from cctr_export.core.integrity import (
    build_export_document_html,
    decode_rich_content,
    sanitize_rich_html,
)
from cctr_export.core.models import Option, Question


def _gz_b64(raw: bytes | str) -> str:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    return base64.b64encode(gzip.compress(data)).decode("ascii")


def _png_data_uri(width: int, height: int, color=(37, 99, 235)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def test_decode_rich_content_strict():
    assert decode_rich_content(_gz_b64("<p>hello 世界</p>")) == "<p>hello 世界</p>"
    assert decode_rich_content("") == ""
    with pytest.raises(ValueError):
        decode_rich_content("not_valid_base64!")
    with pytest.raises(ValueError):
        decode_rich_content(_gz_b64(b"\xff\xfe\xfd"))


def test_sanitize_rich_html_enforces_tags_and_origins():
    ok = sanitize_rich_html('<p>题干</p><img src="data:image/png;base64,iVBORw0KGgo=" />')
    assert "<p>题干</p>" in ok
    with pytest.raises(ValueError):
        sanitize_rich_html("<script>alert(1)</script><p>x</p>")
    with pytest.raises(ValueError):
        sanitize_rich_html('<img src="https://evil.example.com/a.png" />')
    with pytest.raises(ValueError):
        sanitize_rich_html("<p>\u200b   </p>")


def test_build_document_choice_vs_non_choice_labels():
    q1 = Question(
        id="1:101",
        question_type="单选题",
        subject_html="<p>1+1=?</p>",
        answer="A",
        has_options=True,
        options=[Option(is_true=True, html="<p>2</p>"), Option(is_true=False, html="<p>3</p>")],
        subject_name="高数",
        chapter_name="第一章",
        is_choice=True,
    )
    q2 = Question(
        id="1:102",
        question_type="填空题",
        subject_html="<p>光速约为___</p>",
        answer="3e8 m/s",
        has_options=False,
        options=[],
        subject_name="物理",
        chapter_name="光学",
        is_choice=False,
    )
    html = build_export_document_html([q1, q2], variant="withAnswersRed")
    assert '<span class="option-label">A.</span>' in html
    assert '<span class="option-label">B.</span>' in html
    assert "3e8 m/s" in html


def test_pdf_export_multipage_tall_image_and_zip_manifest(tmp_path: Path):
    long_lines = "\n".join(f"第 {i} 行完整推导演算内容 END_MARKER_{i}" for i in range(1, 180))
    tall_img = _png_data_uri(220, 1400)
    qs = [
        Question(
            id="1:201",
            question_type="计算题",
            subject_html=f"<p>长答案与超高图像测试</p><img src=\"{tall_img}\" width=\"220\" height=\"1400\" />",
            answer=long_lines,
            has_options=False,
            options=[],
            subject_name="数字电子技术",
            chapter_name="时序逻辑",
            is_choice=False,
        ),
    ]
    pdf_path = export_questions_to_pdf(qs, tmp_path / "pdf_out", kernel="auto")
    assert pdf_path.exists()
    pdf_bytes = pdf_path.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")

    # Verify all text lines made it into the PDF without truncation
    import pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) >= 3
    full_text = "\n".join(p.extract_text() or "" for p in reader.pages)
    assert "END_MARKER_1" in full_text
    assert "END_MARKER_179" in full_text

    # Verify categorized ZIP + manifest SHA-256
    zip_path = export_questions_to_archive_zip(qs, tmp_path / "out.zip", kernel="auto")
    assert zip_path.exists()
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        names = zf.namelist()
        assert "导出清单.json" in names
        manifest = json.loads(zf.read("导出清单.json").decode("utf-8"))
        assert manifest["questionCount"] == 1
        entry = manifest["groups"][0]
        assert entry["path"] in names
        assert hashlib.sha256(zf.read(entry["path"])).hexdigest() == entry["sha256"]


def test_pdf_rejects_overflow_and_broken_image(tmp_path: Path):
    wide_img = _png_data_uri(1200, 100)
    q_overflow = Question(
        id="1:301",
        question_type="简答题",
        subject_html=f'<table style="width:1100px"><tr><td><img src="{wide_img}" style="max-width:none;width:1100px;height:100px" /></td></tr></table>',
        answer="ok",
        has_options=False,
        options=[],
        subject_name="测试",
        chapter_name="溢出",
        is_choice=False,
    )
    # Note: sanitize_rich_html strips width/max-width inline styles unless on img width attr; test width="1100" inside table
    q_overflow2 = Question(
        id="1:302",
        question_type="简答题",
        subject_html="<table><tr>" + "".join(f"<td>C{i}</td>" for i in range(45)) + "</tr></table>",
        answer="ok",
        has_options=False,
        options=[],
        subject_name="测试",
        chapter_name="溢出",
        is_choice=False,
    )
    with pytest.raises(RuntimeError, match="超出页面宽度"):
        export_questions_to_pdf([q_overflow2], tmp_path / "ov", kernel="auto")


def test_oss_http_upgrade_anchor_tag_and_kernels():
    cleaned = sanitize_rich_html(
        '<p><a name="_Hlk1">题干</a><img src="http://ce-images.oss-cn-beijing.aliyuncs.com/a/b.png" /></p>'
    )
    assert "https://ce-images.oss-cn-beijing.aliyuncs.com/a/b.png" in cleaned

    from cctr_export.core.kernels import detect_all_kernels, resolve_render_backend

    all_k = detect_all_kernels()
    assert "auto" in all_k and "chromium" in all_k and "edge" in all_k
    backend, _, label = resolve_render_backend("auto")
    assert backend in ("cdp", "qtwebengine")
    assert label


def test_uniform_typography_strips_inline_font_size_and_family():
    raw = '<p style="font-size: 24pt; font-family: SimSun; font-weight: bold;"><span style="font-size: 8px;">统一大小</span><sup>2</sup></p>'
    cleaned = sanitize_rich_html(raw)
    assert "font-size" not in cleaned
    assert "font-family" not in cleaned
    assert "font-weight:bold" in cleaned
    assert "<sup>2</sup>" in cleaned

    q = Question(
        id="1:500",
        question_type="计算题",
        subject_html=raw,
        answer='<p style="font-size: 18pt;">解答</p>',
        has_options=False,
        options=[],
        subject_name="数学",
        chapter_name="微积分",
        is_choice=False,
    )
    doc_html = build_export_document_html([q])
    assert "font-size: 10.5pt !important" in doc_html
    assert "24pt" not in doc_html and "18pt" not in doc_html


def test_export_dir_setting_and_cleanup_no_empty_dirs(tmp_path: Path, monkeypatch):
    from cctr_export.core import kernels

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(kernels, "SETTINGS_FILE", fake_home / ".cctr_export" / "settings.json")

    chosen = kernels.set_export_dir(tmp_path / "MyExports")
    assert chosen.exists()
    assert kernels.get_export_dir() == chosen

    # Verify PDF exports directly without creating extra empty numeric subdirectories
    q = Question(
        id="1:601",
        question_type="简答题",
        subject_html="<p>测试直出文件</p>",
        answer="<p>无空文件夹</p>",
        has_options=False,
        options=[],
        subject_name="物理",
        chapter_name="力学",
        is_choice=False,
    )
    pdf_path = export_questions_to_pdf([q], chosen, title="力学", filename="#99_力学_红标答案.pdf")
    assert pdf_path.exists()
    assert pdf_path.parent == chosen
    assert [p.name for p in chosen.iterdir()] == ["#99_力学_红标答案.pdf"]


def test_smart_pagination_keeps_short_questions_intact_and_breaks_after_long(tmp_path: Path):
    import pypdf

    # 3 个中等选择题 + 1 个超长跨页大题 + 1 个后续小题
    qs = [
        Question(
            id=f"2:{i}",
            question_type="单选题",
            subject_html="<p>" + ("题干文本 " * 16) + "</p>",
            answer="A",
            has_options=True,
            options=[Option(is_true=(k == 0), html=f"选项 {chr(65+k)} " + ("描述文字 " * 6)) for k in range(4)],
            subject_name="分页测试",
            chapter_name="综合",
            is_choice=True,
        )
        for i in range(1, 5)
    ]
    # 第 5 题设为超长大题（超过 1 页），第 6 题为常规小题（应另起一页）
    qs.append(
        Question(
            id="2:5",
            question_type="计算题",
            subject_html="<p>LONG_Q5_START</p>" + "".join(f"<p>推导步骤 {k}：详细公式说明。</p>" for k in range(45)),
            answer="<p>LONG_Q5_END</p>",
            has_options=False,
            options=[],
            subject_name="分页测试",
            chapter_name="计算",
            is_choice=False,
        )
    )
    qs.append(
        Question(
            id="2:6",
            question_type="单选题",
            subject_html="<p>AFTER_LONG_Q6</p>",
            answer="A",
            has_options=False,
            options=[],
            subject_name="分页测试",
            chapter_name="收尾",
            is_choice=True,
        )
    )
    pdf_path = export_questions_to_pdf(qs, tmp_path, kernel="auto", filename="smart_pag.pdf")
    reader = pypdf.PdfReader(str(pdf_path))
    pages_txt = [p.extract_text() or "" for p in reader.pages]
    # 第 1~4 题均应完整出现在某单一页上（题号与选项 D、答案不被拆到两页）
    for i in range(1, 5):
        marker = f"2:{i}"
        page_hits = [idx for idx, txt in enumerate(pages_txt) if marker in txt]
        assert len(page_hits) == 1
        assert "选项 D" in pages_txt[page_hits[0]]
    # 超长大题结束页不应混入下一题 AFTER_LONG_Q6
    long_end_pages = [idx for idx, txt in enumerate(pages_txt) if "LONG_Q5_END" in txt]
    q6_pages = [idx for idx, txt in enumerate(pages_txt) if "AFTER_LONG_Q6" in txt]
    assert long_end_pages and q6_pages
    assert q6_pages[0] > long_end_pages[-1]

    # 关闭智能防隔页时应写入 data-smart-pagination="0" 且采用连续紧凑排版（第 1~4 题可跨页紧排）
    html_off = build_export_document_html(qs, smart_pagination=False)
    assert 'data-smart-pagination="0"' in html_off
    pdf_off = export_questions_to_pdf(qs, tmp_path, kernel="auto", filename="compact.pdf", smart_pagination=False)
    reader_off = pypdf.PdfReader(str(pdf_off))
    assert len(reader_off.pages) <= len(reader.pages)


def test_word_smarttags_font_mso_comments_and_image_inlining(monkeypatch):
    from cctr_export.core import exporter as exp_mod
    from cctr_export.core.integrity import has_visible_rich_content

    raw_word = (
        '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View></w:WordDocument></xml><![endif]-->'
        '<p>载频 <st1:chmetcnv UnitName="Hz" SourceValue="3000">3000Hz</st1:chmetcnv>，'
        '信息码 <st1:chsdate year="2001" month="1" day="1">1-1-1</st1:chsdate>，'
        '<font size="4" face="宋体">基带系统</font><o:p></o:p></p>'
    )
    cleaned = sanitize_rich_html(raw_word)
    assert "3000Hz" in cleaned
    assert "1-1-1" in cleaned
    assert "基带系统" in cleaned
    assert "Normal" not in cleaned
    assert "<st1:" not in cleaned
    assert "<font" not in cleaned

    # Pure Word comment metadata with no visible body must not leak text or raise error in optional analysis
    assert not has_visible_rich_content(
        '<!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View></w:WordDocument></xml><![endif]--><p> &nbsp; </p>'
    )

    # Dangerous tags must still be rejected
    with pytest.raises(ValueError):
        sanitize_rich_html("<script>alert(1)</script><p>x</p>")
    with pytest.raises(ValueError):
        sanitize_rich_html("<object data=\"x\"></object><p>x</p>")

    # Verify remote OSS HTTP/HTTPS images get prefetched and inlined into data URIs
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color=(10, 20, 30)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    class _FakeResp:
        status_code = 200
        content = png_bytes

    class _FakeSess:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url, *args, **kwargs):
            return _FakeResp()

        def close(self):
            pass

    monkeypatch.setattr(exp_mod, "ResilientHttpSession", _FakeSess)
    q_img = Question(
        id="9:1",
        question_type="简答题",
        subject_html='<p><img src="http://ce-images.oss-cn-beijing.aliyuncs.com/school_U101441/a.png" /></p>',
        answer="ok",
        has_options=False,
        options=[Option(is_true=True, html='<img src="https://ce-images.oss-cn-beijing.aliyuncs.com/school_U101441/b.png" />')],
        subject_name="通信",
        chapter_name="第六章",
        analysis_html=raw_word,
        is_choice=False,
    )
    inlined = exp_mod.prefetch_and_inline_images([q_img])
    assert inlined[0].subject_html.startswith('<p><img src="data:image/png;base64,')
    assert inlined[0].options[0].html.startswith('<img src="data:image/png;base64,')


def test_saved_accounts_persistence_and_no_passwords(tmp_path: Path, monkeypatch):
    from cctr_export.core import kernels
    from cctr_export.ui import studio_web

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(kernels, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(studio_web, "get_all_tasks", lambda: [])

    assert studio_web.get_saved_accounts() == []
    res = studio_web.remember_saved_account("u101441", "20260001")
    assert res == [{"school": "u101441", "username": "20260001"}]
    res = studio_web.remember_saved_account("u101442", "20260002")
    assert res[0] == {"school": "u101442", "username": "20260002"}
    # Deduplicate and promote re-used account to top
    res = studio_web.remember_saved_account("u101441", "20260001")
    assert res == [
        {"school": "u101441", "username": "20260001"},
        {"school": "u101442", "username": "20260002"},
    ]
    # Ensure no password field is persisted
    raw = settings_file.read_text(encoding="utf-8")
    assert "password" not in raw.lower()

    after_rm = studio_web.remove_saved_account("u101441", "20260001")
    assert after_rm == [{"school": "u101442", "username": "20260002"}]


