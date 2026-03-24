"""题目导出：HTML→图片/PDF，打包 ZIP"""
from __future__ import annotations
import io
import os
import zipfile
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from PIL import Image
from .models import Question
from .driver import create_driver


# 渲染 HTML 模板（CSS 的 { } 全部双写转义，保留 format 占位符）
_RENDER_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; padding: 24px; max-width: 900px; margin: 0 auto; background: #fff; }}
    .question {{ margin-bottom: 16px; line-height: 1.8; font-size: 15px; }}
    .answer {{ margin-top: 12px; padding: 8px 12px; background: #f0f9ff; border-left: 4px solid #0ea5e9; border-radius: 4px; }}
    .option {{ padding: 4px 0; }}
    .option.correct {{ color: #dc2626; font-weight: bold; background: #fef2f2; padding: 4px 8px; border-radius: 4px; display: inline-block; margin: 2px 0; }}
    .label {{ font-size: 13px; color: #64748b; margin-bottom: 4px; }}
</style>
</head>
<body>
<div class="question">{subject_html}</div>
{options_html}
<div class="answer"><div class="label">答案</div>{answer_html}</div>
</body>
</html>
"""


def _build_html(question: Question) -> str:
    options_html = ""
    if question.has_options and question.options:
        opts = []
        for opt in question.options:
            if opt.is_true:
                opts.append(f'<div class="option correct">{opt.html}</div>')
            else:
                opts.append(f'<div class="option">{opt.html}</div>')
        options_html = "<div>" + "".join(opts) + "</div>"

    return _RENDER_TEMPLATE.format(
        subject_html=question.subject_html or "(无题目内容)",
        options_html=options_html,
        answer_html=question.answer or "(无答案)",
    )


def _html_to_image(driver, html: str) -> Image.Image:
    """用 Edge 渲染本地 HTML 文件为 PIL Image"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', encoding='utf-8', delete=False) as f:
        f.write(html)
        f.flush()
        temp_path = f.name

    try:
        file_url = "file:///" + temp_path.replace("\\", "/")
        driver.get(file_url)
        driver.implicitly_wait(0)

        total_width = driver.execute_script("return document.body.scrollWidth")
        total_height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(max(total_width, 800), max(total_height, 200))

        body = driver.find_element("tag name", "body")
        png_data = body.screenshot_as_png
        return Image.open(io.BytesIO(png_data))

    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


# ---------- 并行渲染 worker ----------
_worker_local = threading.local()


def _get_driver():
    """获取当前线程的 driver（懒创建）"""
    if not hasattr(_worker_local, "driver") or _worker_local.driver is None:
        _worker_local.driver = create_driver()
    return _worker_local.driver


def _render_one(args) -> tuple[int, Image.Image]:
    """渲染一道题目，返回 (index, image)"""
    idx, html = args
    driver = _get_driver()
    img = _html_to_image(driver, html)
    return idx, img


def export_questions_to_images(
    questions: list[Question],
    output_dir: str | Path,
    driver_pool=None,
    progress_callback=None,
) -> Path:
    """导出题目为 PNG 图片"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 预建所有 HTML
    items = [(i, _build_html(q)) for i, q in enumerate(questions)]

    done = [0]
    lock = threading.Lock()

    def callback(fut):
        idx, img = fut.result()
        img.save(str(output_dir / f"q_{idx+1:04d}.png"), "PNG")
        with lock:
            done[0] += 1
            if progress_callback:
                progress_callback(done[0], len(questions))

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_render_one, item) for item in items]
        for f in futures:
            f.add_done_callback(callback)

    return output_dir


def export_questions_to_pdf(
    questions: list[Question],
    output_dir: str | Path,
    driver_pool=None,
    progress_callback=None,
) -> Path:
    """导出题目为 PDF（并行渲染）"""
    import img2pdf

    img_dir = output_dir if isinstance(output_dir, Path) else Path(output_dir)
    temp_dir = img_dir / "_temp_png"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 预建所有 HTML
    items = [(i, _build_html(q)) for i, q in enumerate(questions)]

    results: dict[int, Image.Image] = {}
    results_lock = threading.Lock()
    done = [0]

    def callback(fut):
        idx, img = fut.result()
        with results_lock:
            results[idx] = img
            done[0] += 1
            if progress_callback:
                progress_callback(done[0], len(questions))

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_render_one, item) for item in items]
        for f in futures:
            f.add_done_callback(callback)

    # 等待全部完成
    for f in futures:
        f.result()

    # 按顺序保存 PNG
    for idx in sorted(results):
        results[idx].save(str(temp_dir / f"q_{idx+1:04d}.png"), "PNG")

    # 合并 PDF
    pdf_path = img_dir / "output.pdf"
    pngs = sorted(temp_dir.glob("*.png"))
    if pngs:
        with open(str(pdf_path), "wb") as f:
            f.write(img2pdf.convert([str(p) for p in pngs]))

    # 清理
    for p in pngs:
        p.unlink()
    temp_dir.rmdir()

    # 关闭所有 worker driver
    if hasattr(_worker_local, "driver") and _worker_local.driver:
        try:
            _worker_local.driver.quit()
        except Exception:
            pass
        _worker_local.driver = None

    return pdf_path


def pack_to_zip(source_dir: str | Path, zip_path: str | Path) -> Path:
    """将目录打包为 ZIP"""
    source_dir = Path(source_dir)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source_dir.rglob("*")):
            if file.is_file():
                arcname = file.relative_to(source_dir)
                zf.write(str(file), str(arcname))
    return zip_path
