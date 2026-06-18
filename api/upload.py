# api/upload.py
import os
import shutil
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.store import get_user_by_email
from core.utils import verify_token_and_user, verify_admin, get_user_dir
from core.logger import write_log

upload_router = APIRouter(prefix="/api/files", tags=["文件管理"])

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}


class FileInfo(BaseModel):
    name: str
    size: int
    modified: str
    is_dir: bool


def _resolve_user_dir(username: str) -> str:
    """返回用户文件目录路径"""
    return get_user_dir(username)


def _ensure_dir(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)


def _get_safe_path(base_dir: str, subpath: str) -> str:
    """将子路径解析为安全绝对路径，防止目录穿越"""
    safe = os.path.normpath(subpath).lstrip("/").lstrip("\\")
    if safe.startswith("..") or os.path.isabs(safe):
        raise HTTPException(status_code=400, detail="Invalid path")
    target = os.path.join(base_dir, safe)
    if not os.path.abspath(target).startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _list_dir(path: str, recursive: bool = False, base_path: str = "") -> List[FileInfo]:
    """列出目录内容，支持递归/非递归"""
    result = []
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
        for entry in entries:
            name = os.path.relpath(entry.path, base_path).replace("\\", "/") if recursive else entry.name
            if entry.is_dir():
                result.append(FileInfo(
                    name=name + "/", size=0,
                    modified=datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                    is_dir=True,
                ))
                if recursive:
                    result.extend(_list_dir(entry.path, recursive=True, base_path=base_path))
            else:
                result.append(FileInfo(
                    name=name, size=entry.stat().st_size,
                    modified=datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
                    is_dir=False,
                ))
    except PermissionError:
        pass
    return result


# ==================== 文件列表 ====================

@upload_router.get("/list", response_model=List[FileInfo])
def list_files(
    subpath: str = "",
    current_user: str = Depends(verify_token_and_user),
):
    """列出当前用户指定目录下的文件（单层，非递归）"""
    user_dir = _resolve_user_dir(current_user)
    _ensure_dir(user_dir)

    target_dir = _get_safe_path(user_dir, subpath) if subpath else user_dir
    if subpath and not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="目录不存在")

    return _list_dir(target_dir)


# ==================== 批量上传 ====================

@upload_router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    subpath: str = Form(""),
    overwrite: bool = Form(True),
    current_user: str = Depends(verify_token_and_user),
):
    """批量上传 PDF 文件（仅限 .pdf，单文件最大 100MB）
    
    overwrite=False 时，若同名文件已存在则跳过（不覆盖）
    """
    user_dir = _resolve_user_dir(current_user)
    _ensure_dir(user_dir)

    target_dir = _get_safe_path(user_dir, subpath) if subpath else user_dir
    if subpath and not os.path.isdir(target_dir):
        raise HTTPException(status_code=404, detail="目录不存在")

    uploaded = []
    failed = []

    for file in files:
        if not file.filename:
            failed.append({"filename": file.filename or "未知文件", "reason": "文件名无效"})
            continue
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            failed.append({"filename": file.filename, "reason": f"不支持的格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}"})
            continue

        safe_name = os.path.basename(file.filename)
        file_path = os.path.join(target_dir, safe_name)

        # 如果文件已存在且不允许覆盖，跳过
        if os.path.exists(file_path) and not overwrite:
            failed.append({"filename": file.filename, "reason": "文件已存在，已跳过"})
            continue

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            failed.append({"filename": file.filename, "reason": "文件超过 100MB 限制"})
            continue

        with open(file_path, "wb") as f:
            f.write(content)

        uploaded.append({"filename": file.filename, "size": len(content)})
        write_log(current_user, f"上传文件: {file.filename}", "成功",
                  f"大小: {len(content)} bytes, 目录: {subpath or '根目录'}")

    return {"uploaded": uploaded, "failed": failed}


# ==================== 检查文件是否已存在 ====================

class CheckExistsRequest(BaseModel):
    filenames: List[str]
    subpath: str = ""


class CheckExistsResponse(BaseModel):
    existing: List[str]  # 已存在的文件名列表


@upload_router.post("/check-exists", response_model=CheckExistsResponse)
def check_files_exist(
    data: CheckExistsRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """检查指定文件名在用户目录下是否已存在，返回已存在的文件名列表"""
    user_dir = _resolve_user_dir(current_user)
    target_dir = _get_safe_path(user_dir, data.subpath) if data.subpath else user_dir

    existing = []
    for name in data.filenames:
        safe_name = os.path.basename(name)
        if os.path.exists(os.path.join(target_dir, safe_name)):
            existing.append(name)

    return CheckExistsResponse(existing=existing)


# ==================== 下载文件 ====================

@upload_router.get("/download")
def download_file(
    path: str,
    current_user: str = Depends(verify_token_and_user),
):
    """下载指定文件"""
    user_dir = _resolve_user_dir(current_user)
    target = _get_safe_path(user_dir, path)

    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(target, filename=os.path.basename(target))


# ==================== 删除文件/目录 ====================

class DeleteRequest(BaseModel):
    paths: List[str]


@upload_router.post("/delete")
def delete_files(
    data: DeleteRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """批量删除文件或目录"""
    user_dir = _resolve_user_dir(current_user)

    deleted = []
    failed = []

    for p in data.paths:
        target = _get_safe_path(user_dir, p)
        if not os.path.exists(target):
            failed.append({"path": p, "reason": "路径不存在"})
            continue
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
                write_log(current_user, f"删除目录: {p}", "成功")
            else:
                os.remove(target)
                write_log(current_user, f"删除文件: {p}", "成功")
            deleted.append(p)
        except Exception as e:
            failed.append({"path": p, "reason": str(e)})
            write_log(current_user, f"删除: {p}", "失败", str(e))

    return {"deleted": deleted, "failed": failed}


# ==================== 创建目录 ====================

class MkdirRequest(BaseModel):
    name: str
    subpath: str = ""


@upload_router.post("/mkdir")
def make_directory(
    data: MkdirRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """在指定目录下创建子目录"""
    user_dir = _resolve_user_dir(current_user)

    safe_name = os.path.basename(data.name.strip())
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="无效的目录名")

    parent_dir = _get_safe_path(user_dir, data.subpath) if data.subpath else user_dir
    if data.subpath and not os.path.isdir(parent_dir):
        raise HTTPException(status_code=404, detail="父目录不存在")

    target = os.path.join(parent_dir, safe_name)
    if os.path.exists(target):
        raise HTTPException(status_code=400, detail="目录已存在")

    os.makedirs(target)
    write_log(current_user, f"创建目录: {safe_name}", "成功", f"上级目录: {data.subpath or '根目录'}")
    return {"message": f"目录 '{safe_name}' 创建成功"}


# ==================== 重命名文件/目录 ====================

class RenameRequest(BaseModel):
    old_name: str
    new_name: str
    subpath: str = ""


@upload_router.post("/rename")
def rename_file(
    data: RenameRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """重命名指定目录下的文件或目录"""
    user_dir = _resolve_user_dir(current_user)

    safe_old = os.path.basename(data.old_name.strip())
    safe_new = os.path.basename(data.new_name.strip())

    if not safe_old or safe_old in (".", ".."):
        raise HTTPException(status_code=400, detail="无效的原文件名")
    if not safe_new or safe_new in (".", ".."):
        raise HTTPException(status_code=400, detail="无效的新文件名")

    parent_dir = _get_safe_path(user_dir, data.subpath) if data.subpath else user_dir
    if data.subpath and not os.path.isdir(parent_dir):
        raise HTTPException(status_code=404, detail="父目录不存在")

    old_path = os.path.join(parent_dir, safe_old)
    new_path = os.path.join(parent_dir, safe_new)

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="文件或目录不存在")
    if os.path.exists(new_path) and old_path != new_path:
        raise HTTPException(status_code=400, detail="目标文件名已存在")

    os.rename(old_path, new_path)
    write_log(current_user, f"重命名: {safe_old} -> {safe_new}", "成功", f"目录: {data.subpath or '根目录'}")
    return {"message": f"已重命名为 '{safe_new}'"}


# ==================== 管理员操作 ====================

@upload_router.get("/admin/list")
def admin_list_files(
    email: str,
    current_user: str = Depends(verify_admin),
):
    """管理员查看指定用户的文件（递归）"""
    if not get_user_by_email(email):
        raise HTTPException(status_code=404, detail="用户不存在")
    user_dir = get_user_dir(email)
    _ensure_dir(user_dir)
    return _list_dir(user_dir, recursive=True, base_path=user_dir)
