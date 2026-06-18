"""
JSON 文件存储 — 用户信息 + 操作日志
使用线程锁保证并发安全
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, TypedDict

from core.config import get_app_dir 

_DATA_DIR = os.path.join(get_app_dir(), "data")
os.makedirs(_DATA_DIR, exist_ok=True)

_USERS_FILE = os.path.join(_DATA_DIR, "users.json")
_LOGS_FILE  = os.path.join(_DATA_DIR, "logs.json")
_LOCK = threading.Lock()

# ==================== 类型定义 ====================

class UserDict(TypedDict):
    """用户数据字典结构"""
    id: int
    email: str
    display_name: str
    password: str
    is_admin: bool
    is_disable: bool
    force_password_change: bool
    create_time: str
    update_time: str

# ==================== 底层读写 ====================

def _read_json(path: str) -> list[dict[str, Any]]:
    """读取 JSON 文件返回列表，文件不存在则返回空列表"""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: list[dict[str, Any]]) -> None:
    """原子写入 JSON 文件"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ==================== 用户操作 ====================

def get_users() -> list[dict[str, Any]]:
    """获取所有用户"""
    with _LOCK:
        return _read_json(_USERS_FILE)


def get_user_by_email(email: str) -> UserDict | None:
    """根据邮箱查找用户"""
    for u in get_users():
        if u.get("email") == email:
            return u  # pyright: ignore[reportReturnType]
    return None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    """根据 ID 查找用户"""
    for u in get_users():
        if u.get("id") == user_id:
            return u
    return None


def _next_id(users: list[dict[str, Any]]) -> int: 
    if not users:
        return 1
    return max(u["id"] for u in users) + 1 


def create_user(email: str, password: str, display_name: str = "", is_admin: bool = False) -> dict[str, Any]:
    """创建用户，返回用户字典"""
    with _LOCK:
        users = _read_json(_USERS_FILE)
        # 第一个用户自动设为管理员
        if not users:
            is_admin = True
        now = datetime.now().isoformat()
        user = {
            "id": _next_id(users),
            "email": email,
            "display_name": display_name,
            "password": password,
            "is_admin": is_admin,
            "is_disable": False,
            "force_password_change": False,
            "create_time": now,
            "update_time": now,
        }
        users.append(user)
        _write_json(_USERS_FILE, users)
        return user


def update_user(user_id: int, **fields: Any) -> dict[str, Any] | None:
    """更新用户字段，返回更新后的用户"""
    with _LOCK:
        users = _read_json(_USERS_FILE)
        for u in users:
            if u["id"] == user_id:
                u.update(fields)
                u["update_time"] = datetime.now().isoformat()
                _write_json(_USERS_FILE, users)
                return u
    return None


def delete_user(user_id: int) -> dict[str, Any] | None:
    """删除用户，返回被删除的用户"""
    with _LOCK:
        users = _read_json(_USERS_FILE)
        for i, u in enumerate(users):
            if u["id"] == user_id:
                users.pop(i)
                _write_json(_USERS_FILE, users)
                return u
    return None


# ==================== 日志操作 ====================

def add_log(username: str, action: str, result: str = "成功", detail: str | None = None) -> None:
    """追加一条操作日志"""
    with _LOCK:
        logs = _read_json(_LOGS_FILE)
        log_id = _next_id(logs)
        logs.append({
            "id": log_id,
            "username": username,
            "action": action,
            "detail": detail,
            "result": result,
            "create_time": datetime.now().isoformat(),
        })
        _write_json(_LOGS_FILE, logs)


def get_logs(page: int = 1, page_size: int = 50, username: str | None = None) -> list[dict[str, Any]]:
    """分页查询日志，支持按用户名筛选"""
    all_logs = _read_json(_LOGS_FILE)
    # 按 id 倒序
    all_logs.sort(key=lambda x: x["id"], reverse=True)
    if username:
        all_logs = [l for l in all_logs if l.get("username") == username]
    start = (page - 1) * page_size
    return all_logs[start:start + page_size]
