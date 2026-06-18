# api/admin.py
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.store import get_user_by_id, update_user, get_logs
from core.utils import verify_admin
from core.logger import write_log

admin_router = APIRouter(prefix="/api/admin", tags=["管理员功能"])


class SetAdminRequest(BaseModel):
    user_id: int
    is_admin: bool


class LogResponse(BaseModel):
    id: int
    username: str
    action: str
    detail: Optional[str] = None
    result: str
    create_time: datetime


@admin_router.post("/set-admin")
def set_admin(data: SetAdminRequest, current_user: str = Depends(verify_admin)):  # pyright: ignore[reportCallInDefaultInitializer]
    """设置或取消用户的管理员权限"""
    db_user = get_user_by_id(data.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if db_user["id"] == 1:
        raise HTTPException(status_code=400, detail="不能修改超级管理员的权限")

    update_user(data.user_id, is_admin=data.is_admin)
    action = "设为管理员" if data.is_admin else "取消管理员"
    write_log(current_user, f"将 {db_user['email']} {action}", "成功")
    return {"message": f"已{action}: {db_user['email']}"}


@admin_router.get("/logs", response_model=List[LogResponse])
def list_logs(
    _current_user: str = Depends(verify_admin),  # pyright: ignore[reportCallInDefaultInitializer]
    page: int = Query(1, ge=1),  # pyright: ignore[reportCallInDefaultInitializer]
    page_size: int = Query(50, ge=1, le=200),  # pyright: ignore[reportCallInDefaultInitializer]
    username: Optional[str] = Query(None, description="按用户名筛选"),  # pyright: ignore[reportCallInDefaultInitializer]
):
    """查看操作日志（管理员专用，分页）"""
    return get_logs(page=page, page_size=page_size, username=username)
