# api/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.store import get_user_by_email
from core.utils import create_access_token, verify_password, verify_token_and_user
from core.logger import write_log

auth_router = APIRouter(prefix="/api/auth", tags=["认证管理"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserInfoResponse(BaseModel):
    email: str
    display_name: str
    is_admin: bool = False
    force_password_change: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfoResponse


@auth_router.post("/login", response_model=LoginResponse)
def login(user: LoginRequest):
    email = user.email.strip().lower()
    db_user = get_user_by_email(email)
    if not db_user:
        write_log(email, "登录系统", "失败", "邮箱不存在")
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if db_user.get("is_disable"):
        write_log(email, "登录系统", "失败", "用户已被禁用")
        raise HTTPException(status_code=403, detail="User is disabled")

    if not verify_password(user.password.strip(), db_user["password"]):
        write_log(email, "登录系统", "失败", "密码错误")
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(email)
    write_log(email, "登录系统", "成功")
    return {
        "access_token": token,
        "user": UserInfoResponse(
            email=email,
            display_name=db_user.get("display_name") or email.split("@")[0],
            is_admin=bool(db_user.get("is_admin")),
            force_password_change=bool(db_user.get("force_password_change")),
        ),
    }


@auth_router.get("/me", response_model=UserInfoResponse)
def get_me(current_user: str = Depends(verify_token_and_user)):
    """获取当前登录用户信息"""
    db_user = get_user_by_email(current_user)
    return UserInfoResponse(
        email=db_user["email"],
        display_name=db_user.get("display_name") or db_user["email"].split("@")[0],
        is_admin=bool(db_user.get("is_admin")),
        force_password_change=bool(db_user.get("force_password_change")),
    )
