"""任务执行引擎（后台线程）"""
from __future__ import annotations
import threading
from typing import Callable, Optional
from .database import (
    TaskRecord, TaskStatus, ExportType, LogLevel,
    get_task, update_task_status, add_log
)
from .api import CCTRClient
from .models import Practice, ChapterType, QuestionType
from .driver import DriverPool
from .exporter import export_questions_to_images, export_questions_to_pdf, pack_to_zip
from pathlib import Path


class TaskEngine:
    """管理后台任务执行"""
    def __init__(self):
        self._running = False
        self._pool = DriverPool(max_size=2)
        self._progress_callbacks: dict[int, Callable] = {}
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
        """在后台线程执行任务"""
        t = threading.Thread(target=self._run, args=(task_id,), daemon=True)
        t.start()

    def _run(self, task_id: int):
        task = get_task(task_id)
        if not task:
            return

        update_task_status(task_id, TaskStatus.PROCESSING)
        add_log(task_id, LogLevel.INFO, "任务开始执行")

        client: Optional[CCTRClient] = None
        try:
            # 1. 认证（优先复用创建任务时已通过图形验证码登录的会话 key）
            client = CCTRClient(task.school_id, task.username, task.password)
            if task.auth_key:
                add_log(task_id, LogLevel.INFO, "使用创建任务时的登录会话")
                client.key = task.auth_key
            else:
                add_log(task_id, LogLevel.WARN,
                        "任务未携带登录会话，尝试直接登录；若提示验证码错误，请在「添加任务」页重新创建任务")
                add_log(task_id, LogLevel.INFO, f"正在登录: {task.username}")
                client.login()
                add_log(task_id, LogLevel.INFO, "登录成功")

            # 2. 获取题目
            all_questions = []
            for cfg in task.config:
                practice = Practice.from_json(cfg["practice"])
                chapters = [ChapterType.from_dict(c) for c in cfg.get("chapters", [])]
                qtypes = [QuestionType.from_dict(q) for q in cfg.get("question_types", [])]

                add_log(task_id, LogLevel.INFO, f"获取题目: {practice.practice_name}")
                qs = client.query_questions(
                    practice,
                    chapters=chapters or None,
                    question_types=qtypes or None,
                )
                all_questions.extend(qs)
                add_log(task_id, LogLevel.INFO, f"获取到 {len(qs)} 道题目")

            if not all_questions:
                add_log(task_id, LogLevel.WARN, "没有获取到任何题目")
                update_task_status(task_id, TaskStatus.FAILED)
                add_log(task_id, LogLevel.ERROR, "任务失败：无题目")
                return

            add_log(task_id, LogLevel.INFO, f"共 {len(all_questions)} 道题目，开始导出")

            # 3. 导出
            output_base = Path.home() / ".cctr_export" / "output" / str(task_id)
            output_base.mkdir(parents=True, exist_ok=True)

            def progress(cur, tot):
                self._report_progress(task_id, cur, tot)

            if task.export_type == ExportType.IMG:
                export_questions_to_images(all_questions, output_base, self._pool, progress)
                # 打包 ZIP
                zip_path = Path.home() / ".cctr_export" / "output" / f"task_{task_id}.zip"
                pack_to_zip(output_base, zip_path)
                add_log(task_id, LogLevel.INFO, f"导出完成: {zip_path}")
            else:
                pdf_path = export_questions_to_pdf(all_questions, output_base, self._pool, progress)
                zip_path = Path.home() / ".cctr_export" / "output" / f"task_{task_id}.zip"
                pack_to_zip(output_base, zip_path)
                add_log(task_id, LogLevel.INFO, f"导出完成: {zip_path}")

            update_task_status(task_id, TaskStatus.SUCCESS)
            add_log(task_id, LogLevel.INFO, "任务完成")

        except Exception as e:
            update_task_status(task_id, TaskStatus.FAILED)
            add_log(task_id, LogLevel.ERROR, f"任务失败: {str(e)}")
        finally:
            if client:
                client.close()

    def shutdown(self):
        self._pool.close_all()


# 全局引擎实例
engine = TaskEngine()
