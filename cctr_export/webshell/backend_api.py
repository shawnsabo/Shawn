"""命令实现 — 严格对应 Tauri(Rust) 版前端已逆向出的 API 契约

命令：list_browsers / auth_login / practice_metadata / list_tasks / create_task /
      open_output / list_logs / clear_logs / open_log_dir
事件：tasks_changed / logs_changed（payload 为完整数组）

数据形状（与前端 JS 期望一致，camelCase）：
  Practice: {id, practiceName, lessonName, courseId, practiseId, teacherId}
  Chapter/QuestionType: {id, name}
  Browser: {type, name, available, version, reason?}
  Task: {id, status, username, exportType, answerVariants, practiceCount,
         progress:{total,current,label}, error}
  Log: {id, taskId, level, message, createdAt}
"""
import base64
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..core.api import CCTRClient
from ..core.models import Practice, ChapterType, QuestionType
from ..core.database import (
    add_task, get_all_tasks, get_task, update_task_status, add_log,
    get_all_logs, clear_all_logs, ExportType, TaskStatus, LogLevel,
)
from ..core.exporter import (
    export_questions_to_pdf, export_questions_to_images, pack_to_zip,
)
from . import captcha

OUTPUT_DIR = Path.home() / ".cctr_export" / "output"
VARIANT_LABELS = {
    "withAnswersRed": "带答案-红色标注",
    "withAnswersPlain": "带答案-不标红",
    "withoutAnswers": "不带答案",
}

_lock = threading.Lock()
_sessions = {}   # username -> {"client": CCTRClient, "schoolId": str, "password": str}
_progress = {}   # task_id -> {"total": int, "current": int, "label": str}
_errors = {}     # task_id -> str
_emitter = None  # app.py 注入：fn(event_name, payload_dict)
_pending_client = None   # 登录界面验证码所属的会话客户端（与网页登录同源行为）
_pending_code = None     # 登录界面提交的验证码


def set_event_emitter(fn):
    global _emitter
    _emitter = fn


def _emit(event, payload):
    if _emitter:
        try:
            _emitter(event, payload)
        except Exception:
            pass


def _emit_tasks():
    _emit("tasks_changed", _cmd_list_tasks({}))


def _emit_logs():
    _emit("logs_changed", _cmd_list_logs({}))


# ── 命令入口 ─────────────────────────────────────────────────────

def dispatch(cmd, args):
    handler = {
        "list_browsers": _cmd_list_browsers,
        "auth_login": _cmd_auth_login,
        "practice_metadata": _cmd_practice_metadata,
        "list_tasks": _cmd_list_tasks,
        "create_task": _cmd_create_task,
        "open_output": _cmd_open_output,
        "list_logs": _cmd_list_logs,
        "clear_logs": _cmd_clear_logs,
        "open_log_dir": _cmd_open_log_dir,
        "get_captcha": _cmd_get_captcha,
        "set_captcha": _cmd_set_captcha,
    }.get(cmd)
    if handler is None:
        raise RuntimeError(f"未知命令: {cmd}")
    return handler(args or {})


# ── 形状转换 ─────────────────────────────────────────────────────

def _practice_to_js(p: Practice) -> dict:
    return {
        "id": p.id,
        "practiceName": p.practice_name,
        "lessonName": p.lesson_name,
        "courseId": p.courseid,
        "practiseId": p.practise_id,
        "teacherId": p.teacher_id,
    }


def _practice_from_js(d: dict) -> Practice:
    d = d or {}
    return Practice(
        id=int(d.get("id") or 0),
        courseid=str(d.get("courseId") or d.get("courseid") or ""),
        practise_id=str(d.get("practiseId") or d.get("practise_id") or ""),
        teacher_id=str(d.get("teacherId") or d.get("teacher_id") or ""),
        lesson_name=str(d.get("lessonName") or d.get("lesson_name") or ""),
        practice_name=str(d.get("practiceName") or d.get("practice_name") or ""),
        teacher_name="", finish_time="",
    )


# ── 登录（含验证码：OCR 优先 / 原生对话框兜底） ──────────────────

def _captcha_login(school: str, user: str, pwd: str, max_attempts: int = 5) -> CCTRClient:
    client = CCTRClient(school, user, pwd)
    last_err = None
    for _ in range(max_attempts):
        try:
            img = client.fetch_captcha()
            code = captcha.solve(img, f"登录 {user}")
            if not code:
                raise RuntimeError("验证码为空")
            client.login(captcha=code)
            return client
        except RuntimeError as e:
            last_err = e
            if "验证码" in str(e):
                continue
            raise
    raise RuntimeError(f"验证码识别失败（已尝试 {max_attempts} 次）：{last_err}")


def _get_client(user: str) -> CCTRClient | None:
    with _lock:
        sess = _sessions.get(user)
    return sess["client"] if sess else None


# ── 命令实现 ─────────────────────────────────────────────────────

def _cmd_list_browsers(args):
    from ..browser.chrome import ChromeBrowser
    from ..browser.edge import EdgeBrowser
    out = []
    for b in (ChromeBrowser(), EdgeBrowser()):
        ver = b.get_version()
        item = {"type": b.browser_type, "name": b.name, "available": bool(ver),
                "version": ver or ""}
        if not ver:
            item["reason"] = "未安装"
        out.append(item)
    return out


def _cmd_auth_login(args):
    global _pending_client, _pending_code
    payload = args.get("payload") or {}
    school = str(payload.get("schoolId", "")).strip()
    user = str(payload.get("username", "")).strip()
    pwd = str(payload.get("password", ""))
    if not school or not user or not pwd:
        raise RuntimeError("请先填学校代码、账号和密码。")

    # 优先使用登录界面（注入 UI）提交的验证码：同会话客户端，与网页登录行为一致
    with _lock:
        client, code = _pending_client, _pending_code
        _pending_code = None

    if client is None:
        # 兜底：注入 UI 不可用时走 OCR / 原生对话框
        client = _captcha_login(school, user, pwd)
    elif not code:
        raise RuntimeError("请先输入图形验证码。")
    else:
        client.school_id, client.username, client.password = school, user, pwd
        try:
            client.login(captcha=code)
        except RuntimeError as e:
            if "验证码" in str(e):
                pass  # 旧验证码已作废，注入 UI 会自动刷新图片
            raise

    practices = client.get_practice_list()
    with _lock:
        _sessions[user] = {"client": client, "schoolId": school, "password": pwd}
        _pending_client = None
    return [_practice_to_js(p) for p in practices]


def _cmd_get_captcha(args):
    """获取图形验证码（base64 data URL）。验证码与会话 Cookie 绑定，
    本命令持有的客户端即后续 auth_login 使用的客户端。"""
    global _pending_client, _pending_code
    with _lock:
        client = _pending_client
        if client is None:
            client = CCTRClient("", "", "")
        img = client.fetch_captcha()
        _pending_client = client
        _pending_code = None  # 刷新即作废旧验证码
    return {"image": "data:image/png;base64," + base64.b64encode(img).decode("ascii")}


def _cmd_set_captcha(args):
    global _pending_code
    with _lock:
        _pending_code = str(args.get("code", "")).strip()
    return True


def _cmd_practice_metadata(args):
    payload = args.get("payload") or {}
    user = str(payload.get("username", "")).strip()
    client = _get_client(user)
    if client is None:
        client = _captcha_login(str(payload.get("schoolId", "")).strip(), user,
                                str(payload.get("password", "")))
    practice = _practice_from_js(payload.get("practice") or {})
    chapters, qtypes = client.get_chapter_and_question_type(practice)
    return {
        "chapters": [{"id": c.id, "name": c.name} for c in chapters],
        "questionTypes": [{"id": q.id, "name": q.name} for q in qtypes],
    }


def _cmd_list_tasks(args):
    out = []
    for t in get_all_tasks():
        cfg = t.config
        prog = dict(_progress.get(t.id, {"total": 0, "current": 0, "label": ""}))
        if isinstance(cfg, dict):
            variants = cfg.get("answerVariants") or []
            pcount = len(cfg.get("practices") or [])
            et = cfg.get("exportType") or ("pdf" if t.export_type == ExportType.PDF else "png")
        else:
            variants = []
            pcount = len(cfg) if isinstance(cfg, list) else 0
            et = "pdf" if t.export_type == ExportType.PDF else "png"
        out.append({
            "id": t.id, "status": t.status.value, "username": t.username,
            "exportType": et, "answerVariants": variants, "practiceCount": pcount,
            "progress": prog, "error": _errors.get(t.id, ""),
        })
    return out


def _cmd_create_task(args):
    cfg = args.get("config") or {}
    user = str(cfg.get("username", "")).strip()
    if not user:
        raise RuntimeError("配置缺少账号")
    export_type = ExportType.PDF if cfg.get("exportType") == "pdf" else ExportType.IMG
    with _lock:
        sess = _sessions.get(user)
    auth_key = sess["client"].key if sess else ""
    tid = add_task(str(cfg.get("schoolId", "")), user, str(cfg.get("password", "")),
                   export_type, cfg, auth_key=auth_key)
    threading.Thread(target=_run_web_task, args=(tid, cfg), daemon=True).start()
    return {"taskId": tid}


def _cmd_open_output(args):
    tid = args.get("taskId")
    zip_path = OUTPUT_DIR / f"task_{tid}.zip"
    if not zip_path.exists():
        raise RuntimeError(f"导出文件不存在：{zip_path}")
    import subprocess
    subprocess.Popen(["explorer", "/select,", str(zip_path)])
    return True


def _cmd_list_logs(args):
    return [{
        "id": r["id"], "taskId": r["task_id"], "level": r["level"],
        "message": r["message"], "createdAt": r["create_time"],
    } for r in get_all_logs()]


def _cmd_clear_logs(args):
    clear_all_logs()
    return True


def _cmd_open_log_dir(args):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(OUTPUT_DIR)
    return True


# ── 任务执行（复用 core 导出管线，支持答案版本/浏览器选择） ──────

def _safe(name: str) -> str:
    return "".join(ch for ch in (name or "") if ch not in '\\/:*?"<>|').strip() or "practice"


def _run_web_task(tid: int, cfg: dict):
    executor = ThreadPoolExecutor(max_workers=4)
    try:
        update_task_status(tid, TaskStatus.PROCESSING)
        add_log(tid, LogLevel.INFO, "任务开始执行")
        _emit_tasks()

        task = get_task(tid)
        client = CCTRClient(str(cfg.get("schoolId", "")),
                            str(cfg.get("username", "")),
                            str(cfg.get("password", "")))
        if task and task.auth_key:
            client.key = task.auth_key
            add_log(tid, LogLevel.INFO, "使用登录会话（创建任务时已通过验证码）")
        else:
            add_log(tid, LogLevel.WARN, "无登录会话，尝试直接登录（当前需验证码，可能失败）")
            client.login()

        practices = [_practice_from_js(p) for p in (cfg.get("practices") or [])]
        chapter_ids = [str(c) for c in (cfg.get("chapters") or [])]
        qtype_ids = [str(q) for q in (cfg.get("questionTypes") or [])]
        variants = cfg.get("answerVariants") or ["withAnswersRed"]
        export_type = str(cfg.get("exportType") or "pdf")
        browser_type = cfg.get("browser") if cfg.get("browser") in ("chrome", "edge") else None

        total = max(1, len(practices) * len(variants))
        _progress[tid] = {"total": total, "current": 0, "label": "准备中"}
        _emit_tasks()

        out_base = OUTPUT_DIR / f"task_{tid}"
        out_base.mkdir(parents=True, exist_ok=True)

        chapter_objs = [ChapterType(id=c, course_id="", name="") for c in chapter_ids] or None
        qtype_objs = [QuestionType(id=q, question_type_id="", name="") for q in qtype_ids] or None

        idx = 0
        for practice in practices:
            qs = client.query_questions(practice, chapters=chapter_objs,
                                        question_types=qtype_objs)
            add_log(tid, LogLevel.INFO, f"{practice.lesson_name} / {practice.practice_name}：{len(qs)} 题")
            for variant in variants:
                idx += 1
                label = f"{practice.practice_name} · {VARIANT_LABELS.get(variant, variant)}（{idx}/{total}）"
                _progress[tid]["current"] = idx - 1
                _progress[tid]["label"] = label
                _emit_tasks()
                sub = out_base / f"{_safe(practice.lesson_name)}_{_safe(practice.practice_name)}_{variant}"
                if export_type == "png":
                    export_questions_to_images(qs, sub, variant=variant, browser_type=browser_type)
                else:
                    export_questions_to_pdf(qs, sub, variant=variant, browser_type=browser_type)
                add_log(tid, LogLevel.INFO, f"完成 {label}（{len(qs)} 题）")
                _progress[tid]["current"] = idx
                _emit_tasks()
            _emit_logs()

        zip_path = OUTPUT_DIR / f"task_{tid}.zip"
        pack_to_zip(out_base, zip_path)
        _progress[tid]["label"] = f"已打包 {zip_path.name}"
        update_task_status(tid, TaskStatus.SUCCESS)
        add_log(tid, LogLevel.INFO, f"任务完成：{zip_path}")
    except Exception as e:
        update_task_status(tid, TaskStatus.FAILED)
        _errors[tid] = str(e)
        add_log(tid, LogLevel.ERROR, f"任务失败：{e}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        _emit_tasks()
        _emit_logs()
