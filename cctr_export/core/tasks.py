"""任务执行引擎（后台线程 + 完整性日志）"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from .api import CCTRClient
from .database import (
    ExportType,
    LogLevel,
    TaskStatus,
    add_log,
    get_task,
    update_task_output_path,
    update_task_status,
)
from .exporter import (
    export_questions_to_archive_zip,
    export_questions_to_images,
    export_questions_to_pdf,
    pack_to_zip,
)
from .formats import (
    export_questions_to_anki_tsv,
    export_questions_to_json,
    export_questions_to_markdown,
    export_questions_to_xlsx,
    load_local_bank_questions,
)
from .integrity import safe_archive_segment
from .kernels import get_export_dir, get_preferred_kernel, resolve_render_backend
from .models import ChapterType, Practice, QuestionType


class TaskEngine:
    """管理后台任务执行"""

    def __init__(self):
        self._progress_callbacks: dict[int, Callable[[int, int], None]] = {}
        self._lock = threading.Lock()

    def set_progress_callback(self, task_id: int, cb: Callable[[int, int], None]):
        with self._lock:
            self._progress_callbacks[task_id] = cb

    def remove_progress_callback(self, task_id: int):
        with self._lock:
            self._progress_callbacks.pop(task_id, None)

    def _report_progress(self, task_id: int, current: int, total: int):
        with self._lock:
            cb = self._progress_callbacks.get(task_id)
        if cb:
            try:
                cb(current, total)
            except Exception:
                pass

    def run_task(self, task_id: int):
        t = threading.Thread(target=self._run, args=(task_id,), daemon=True)
        t.start()

    def _run(self, task_id: int):
        task = get_task(task_id)
        if not task:
            return

        update_task_status(task_id, TaskStatus.PROCESSING)
        add_log(task_id, LogLevel.INFO, "任务开始执行（已启用内容完整性校验）")

        client: Optional[CCTRClient] = None
        try:
            all_questions = []
            variant = "withAnswersRed"
            practiced_only: Optional[bool] = None
            smart_pagination = True

            needs_cctr = any(
                Practice.from_json(cfg["practice"]).courseid != "__local_bank__"
                for cfg in task.config
            )
            if needs_cctr:
                client = CCTRClient(task.school_id, task.username, task.password)
                if task.auth_key:
                    add_log(task_id, LogLevel.INFO, "复用登录会话 key")
                    client.key = task.auth_key
                else:
                    add_log(task_id, LogLevel.WARN, "任务未携带登录会话，请在界面登录后重新提交任务")
                    client.login()

            for cfg in task.config:
                practice = Practice.from_json(cfg["practice"])
                chapters = [ChapterType.from_dict(c) for c in cfg.get("chapters", [])]
                qtypes = [QuestionType.from_dict(q) for q in cfg.get("question_types", [])]
                variant = cfg.get("variant", variant)
                if cfg.get("practiced_only") is True:
                    practiced_only = True
                if cfg.get("smart_pagination") is False:
                    smart_pagination = False

                if practice.courseid == "__local_bank__":
                    add_log(task_id, LogLevel.INFO, f"读取多平台/导入题库: {practice.practice_name}")
                    qs = load_local_bank_questions(
                        practice.practise_id,
                        chapters=chapters or None,
                        question_types=qtypes or None,
                    )
                    all_questions.extend(qs)
                    add_log(task_id, LogLevel.INFO, f"✓ 「{practice.practice_name}」已载入 {len(qs)} 道题目")
                else:
                    assert client is not None
                    add_log(task_id, LogLevel.INFO, f"拉取题目与核对总数: {practice.practice_name}")
                    qs = client.query_questions(
                        practice,
                        chapters=chapters or None,
                        question_types=qtypes or None,
                        practiced=practiced_only,
                    )
                    all_questions.extend(qs)
                    add_log(task_id, LogLevel.INFO, f"✓ 「{practice.practice_name}」获取并核对 {len(qs)} 道题目")

            if not all_questions:
                update_task_status(task_id, TaskStatus.FAILED)
                add_log(task_id, LogLevel.ERROR, "任务失败：未获取到任何题目")
                return

            pref_kernel = get_preferred_kernel()
            is_render_export = task.export_type in (ExportType.PDF, ExportType.ZIP, ExportType.IMG)
            if is_render_export:
                add_log(task_id, LogLevel.INFO, f"共 {len(all_questions)} 道题目，开始渲染并校验图片/页宽...")
                try:
                    _, _, k_label = resolve_render_backend(pref_kernel)
                    add_log(task_id, LogLevel.INFO, f"渲染内核（策略={pref_kernel}）：{k_label}")
                except Exception as k_err:
                    add_log(task_id, LogLevel.ERROR, f"渲染内核未就绪：{k_err}")
                    raise
            else:
                add_log(task_id, LogLevel.INFO, f"共 {len(all_questions)} 道题目，开始转换格式导出...")

            export_root = get_export_dir()
            first_name = ""
            if task.config:
                try:
                    p0 = Practice.from_json(task.config[0]["practice"])
                    first_name = p0.lesson_name or p0.practice_name
                except Exception:
                    pass
            scope_label = safe_archive_segment(first_name or "题库导出")
            if len(task.config) > 1:
                scope_label = f"{scope_label}_等{len(task.config)}项"
            variant_tag = {
                "withAnswersRed": "红标答案",
                "withAnswersPlain": "普通答案",
                "withoutAnswers": "无答案",
            }.get(variant, variant)
            mode_tag = "_仅已练" if practiced_only else ""
            file_stem = f"#{task_id}_{scope_label}{mode_tag}_{variant_tag}"

            def progress(cur: int, tot: int):
                self._report_progress(task_id, cur, tot)

            if task.export_type == ExportType.IMG:
                zip_path = export_root / f"{file_stem}_PNG图包.zip"
                with tempfile.TemporaryDirectory(prefix=f"cctr_img_{task_id}_") as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    export_questions_to_images(all_questions, tmp_path, progress_callback=progress, variant=variant, kernel=pref_kernel)
                    pack_to_zip(tmp_path, zip_path)
                update_task_output_path(task_id, str(zip_path))
                add_log(task_id, LogLevel.INFO, f"✓ PNG 打包完成: {zip_path}")
            elif task.export_type == ExportType.ZIP:
                zip_path = export_root / f"{file_stem}_分类PDF.zip"
                export_questions_to_archive_zip(
                    all_questions,
                    zip_path,
                    progress_callback=progress,
                    variant=variant,
                    kernel=pref_kernel,
                    smart_pagination=smart_pagination,
                )
                update_task_output_path(task_id, str(zip_path))
                add_log(task_id, LogLevel.INFO, f"✓ 分类 PDF + 导出清单.json 完成: {zip_path}")
            elif task.export_type == ExportType.XLSX:
                xlsx_path = export_root / f"{file_stem}_刷题表.xlsx"
                export_questions_to_xlsx(all_questions, xlsx_path, variant=variant, title=scope_label)
                progress(len(all_questions), len(all_questions))
                update_task_output_path(task_id, str(xlsx_path))
                add_log(task_id, LogLevel.INFO, f"✓ 通用 Excel 题库（考试宝/磨题帮）完成: {xlsx_path}")
            elif task.export_type == ExportType.ANKI:
                tsv_path = export_root / f"{file_stem}_Anki记忆卡.tsv"
                export_questions_to_anki_tsv(all_questions, tsv_path, title=scope_label)
                progress(len(all_questions), len(all_questions))
                update_task_output_path(task_id, str(tsv_path))
                add_log(task_id, LogLevel.INFO, f"✓ Anki 记忆卡导入表完成: {tsv_path}")
            elif task.export_type == ExportType.MD:
                md_path = export_root / f"{file_stem}.md"
                export_questions_to_markdown(all_questions, md_path, variant=variant, title=scope_label)
                progress(len(all_questions), len(all_questions))
                update_task_output_path(task_id, str(md_path))
                add_log(task_id, LogLevel.INFO, f"✓ Markdown 讲义完成: {md_path}")
            elif task.export_type == ExportType.JSON:
                json_path = export_root / f"{file_stem}.json"
                export_questions_to_json(all_questions, json_path, variant=variant, title=scope_label)
                progress(len(all_questions), len(all_questions))
                update_task_output_path(task_id, str(json_path))
                add_log(task_id, LogLevel.INFO, f"✓ 标准结构化 JSON 完成: {json_path}")
            else:
                pdf_path = export_questions_to_pdf(
                    all_questions,
                    export_root,
                    progress_callback=progress,
                    variant=variant,
                    kernel=pref_kernel,
                    title=scope_label,
                    filename=f"{file_stem}.pdf",
                    smart_pagination=smart_pagination,
                )
                update_task_output_path(task_id, str(pdf_path))
                add_log(
                    task_id,
                    LogLevel.INFO,
                    f"✓ 合并 A4 PDF 完成（智能防隔页={'开启' if smart_pagination else '关闭'} · 统一字号与公式比例）: {pdf_path}",
                )

            update_task_status(task_id, TaskStatus.SUCCESS)
            add_log(task_id, LogLevel.INFO, "任务完成")
        except Exception as e:
            update_task_status(task_id, TaskStatus.FAILED)
            add_log(task_id, LogLevel.ERROR, f"任务失败: {e}")
        finally:
            if client:
                client.close()

    def shutdown(self):
        pass


engine = TaskEngine()
