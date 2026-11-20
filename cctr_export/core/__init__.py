"""核心模块（惰性导出）"""
from __future__ import annotations

import importlib

_EXPORTS = {
    "CCTRClient": (".api", "CCTRClient"),
    "Practice": (".models", "Practice"),
    "ChapterType": (".models", "ChapterType"),
    "QuestionType": (".models", "QuestionType"),
    "Question": (".models", "Question"),
    "Option": (".models", "Option"),
    "init_db": (".database", "init_db"),
    "TaskRecord": (".database", "TaskRecord"),
    "TaskStatus": (".database", "TaskStatus"),
    "ExportType": (".database", "ExportType"),
    "add_task": (".database", "add_task"),
    "get_all_tasks": (".database", "get_all_tasks"),
    "get_task": (".database", "get_task"),
    "delete_task": (".database", "delete_task"),
    "update_task_status": (".database", "update_task_status"),
    "add_log": (".database", "add_log"),
    "get_logs": (".database", "get_logs"),
    "LogLevel": (".database", "LogLevel"),
    "rsa_encrypt": (".security", "rsa_encrypt"),
    "decompress_gzip_base64": (".security", "decompress_gzip_base64"),
    "export_questions_to_images": (".exporter", "export_questions_to_images"),
    "export_questions_to_pdf": (".exporter", "export_questions_to_pdf"),
    "export_questions_to_archive_zip": (".exporter", "export_questions_to_archive_zip"),
    "pack_to_zip": (".exporter", "pack_to_zip"),
    "task_engine": (".tasks", "engine"),
    "is_ocr_available": (".captcha_ocr", "is_ocr_available"),
    "recognize_captcha": (".captcha_ocr", "recognize_captcha"),
    "ResilientHttpSession": (".http_utils", "ResilientHttpSession"),
    "sniff_image_mime": (".http_utils", "sniff_image_mime"),
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr_name = target
    mod = importlib.import_module(mod_name, __name__)
    val = getattr(mod, attr_name)
    globals()[name] = val
    return val
