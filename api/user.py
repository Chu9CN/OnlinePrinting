from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from pydantic import BaseModel

from core.schemas import UserResponse, UserCreate, UserUpdate
from core.store import get_users, get_user_by_email, get_user_by_id, create_user, update_user, delete_user
from core.utils import verify_admin, verify_token_and_user, to_bcrypt, verify_password, create_user_dir, remove_user_dir
from core.logger import write_log

user_router = APIRouter(prefix="/api/users", tags=["用户管理"])

DEFAULT_RESET_PASSWORD = "000000"


@user_router.get("/list", response_model=List[UserResponse])
def read_users(current_user: str = Depends(verify_admin)):
    return get_users()


@user_router.post("/create", response_model=UserResponse)
def create_user_endpoint(user: UserCreate):
    """注册新用户。系统中第一个注册的用户自动成为超级管理员。"""
    email = user.email.strip().lower()
    plain_password = user.password.strip()

    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    new_user = create_user(
        email=email,
        password=to_bcrypt(plain_password),
        display_name=user.display_name.strip(),
    )

    create_user_dir(new_user["email"])
    write_log(new_user["email"], "注册账号", "成功")
    return new_user


@user_router.delete("/{user_id}", response_model=UserResponse)
def delete_user_endpoint(user_id: int, current_user: str = Depends(verify_admin)):
    db_user = get_user_by_id(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    remove_user_dir(db_user["email"])
    deleted = delete_user(user_id)
    write_log(current_user, f"删除用户: {deleted['email']}", "成功")
    return deleted


@user_router.put("/update/{user_id}", response_model=UserResponse)
def update_user_endpoint(user_id: int, user: UserUpdate, current_user: str = Depends(verify_admin)):
    db_user = get_user_by_id(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = user.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"] is not None:
        update_data["password"] = to_bcrypt(update_data["password"])

    updated = update_user(user_id, **update_data)

    changes = [k for k in update_data if k != "password"]
    detail = "修改: " + ", ".join(changes) if changes else "无字段变更"
    write_log(current_user, f"更新用户 {updated['email']} 信息", "成功", detail)
    return updated


@user_router.post("/reset-password/{user_id}", response_model=UserResponse)
def reset_password(user_id: int, current_user: str = Depends(verify_admin)):
    """管理员重置用户密码为 000000，并强制下次登录修改密码"""
    db_user = get_user_by_id(user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updated = update_user(user_id,
                          password=to_bcrypt(DEFAULT_RESET_PASSWORD),
                          force_password_change=True)
    write_log(current_user, f"重置用户 {updated['email']} 密码", "成功")
    return updated


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    display_name: str


class ProfileResponse(BaseModel):
    email: str
    display_name: str


@user_router.put("/me/update", response_model=ProfileResponse)
def update_my_profile(
    data: UpdateProfileRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """当前用户修改自己的显示名称"""
    display_name = data.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="显示名称不能为空")

    db_user = get_user_by_email(current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    updated = update_user(db_user["id"], display_name=display_name)
    write_log(current_user, "修改显示名称", "成功")
    return {"email": updated["email"], "display_name": updated["display_name"]}


@user_router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """用户自行修改密码（首次登录强制修改也走此接口）"""
    if data.old_password == data.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    db_user = get_user_by_email(current_user)
    if not db_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not verify_password(data.old_password.strip(), db_user["password"]):
        raise HTTPException(status_code=400, detail="旧密码错误")

    update_user(db_user["id"],
                password=to_bcrypt(data.new_password.strip()),
                force_password_change=False)
    write_log(current_user, "修改密码", "成功")
    return {"message": "密码修改成功"}
