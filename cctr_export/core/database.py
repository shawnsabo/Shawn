"""SQLite 任务数据库"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class TaskStatus(str, Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class ExportType(str, Enum):
    PDF = "pdf"
    ZIP = "zip"
    IMG = "img"


class LogLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class TaskRecord:
    id: int
    school_id: str
    username: str
    password: str
    status: TaskStatus
    export_type: ExportType
    create_time: str
    config: list[dict] = field(default_factory=list)  # [{practice, chapters:[], question_types:[]}]
    log: str = ""
    auth_key: str = ""  # 创建任务时通过图形验证码登录得到的会话 key
    output_path: str = ""  # 实际导出文件或归档路径


def _db_path() -> Path:
    p = Path.home() / ".cctr_export" / "tasks.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            export_type TEXT NOT NULL DEFAULT 'pdf',
            create_time TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '[]'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            create_time TEXT NOT NULL
        )
    """)
    # 旧库迁移：tasks 增加 auth_key 列与 output_path 列
    for ddl in (
        "ALTER TABLE tasks ADD COLUMN auth_key TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE tasks ADD COLUMN output_path TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


def add_task(school_id: str, username: str, password: str,
             export_type: ExportType, config: list[dict], auth_key: str = "") -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO tasks (school_id, username, password, status, export_type, create_time, config, auth_key) VALUES (?,?,?,?,?,?,?,?)",
        (school_id, username, password, TaskStatus.WAITING.value, export_type.value,
         datetime.now().isoformat(), json.dumps(config, ensure_ascii=False), auth_key)
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def update_task_status(task_id: int, status: TaskStatus):
    conn = _conn()
    conn.execute("UPDATE tasks SET status=? WHERE id=?", (status.value, task_id))
    conn.commit()
    conn.close()


def update_task_output_path(task_id: int, output_path: str):
    conn = _conn()
    conn.execute("UPDATE tasks SET output_path=? WHERE id=?", (output_path, task_id))
    conn.commit()
    conn.close()


def get_all_tasks() -> list[TaskRecord]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    conn.close()
    return [
        TaskRecord(
            id=r["id"], school_id=r["school_id"], username=r["username"],
            password=r["password"], status=TaskStatus(r["status"]),
            export_type=ExportType(r["export_type"]), create_time=r["create_time"],
            config=json.loads(r["config"]), auth_key=r["auth_key"] or "",
            output_path=(r["output_path"] if "output_path" in r.keys() else "") or "",
        ) for r in rows
    ]


def get_task(task_id: int) -> Optional[TaskRecord]:
    conn = _conn()
    r = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not r:
        return None
    return TaskRecord(
        id=r["id"], school_id=r["school_id"], username=r["username"],
        password=r["password"], status=TaskStatus(r["status"]),
        export_type=ExportType(r["export_type"]), create_time=r["create_time"],
        config=json.loads(r["config"]), auth_key=r["auth_key"] or "",
        output_path=(r["output_path"] if "output_path" in r.keys() else "") or "",
    )


def delete_task(task_id: int):
    conn = _conn()
    conn.execute("DELETE FROM logs WHERE task_id=?", (task_id,))
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


def add_log(task_id: int, level: LogLevel, message: str):
    conn = _conn()
    conn.execute(
        "INSERT INTO logs (task_id, level, message, create_time) VALUES (?,?,?,?)",
        (task_id, level.value, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_logs(task_id: int) -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM logs WHERE task_id=? ORDER BY id ASC", (task_id,)).fetchall()
    conn.close()
    return [{"id": r["id"], "task_id": r["task_id"], "level": r["level"],
             "message": r["message"], "create_time": r["create_time"]} for r in rows]


def get_all_logs(limit: int = 2000) -> list[dict]:
    """最近 limit 条日志，按时间升序返回（前端自行倒序展示）"""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM (SELECT * FROM logs ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_all_logs():
    """清空全部日志"""
    conn = _conn()
    conn.execute("DELETE FROM logs")
    conn.commit()
    conn.close()
