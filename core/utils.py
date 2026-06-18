# utils.py
from __future__ import annotations

import datetime
import os
import shutil

import jwt  # type: ignore[import-untyped]
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core import config
from core import store
from core.store import UserDict


SECRET_KEY = config.SecretKey
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
security = HTTPBearer(auto_error=False)


def to_bcrypt(password: str) -> str:
    """将明文密码哈希为 bcrypt 字符串"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")  


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))  

def create_access_token(email: str) -> str:
    """根据邮箱生成 JWT Token"""
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": email,
        "exp": expire,
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM) 

# ==================== 用户目录路径 ====================

def _sanitize_dir_name(email: str) -> str:
    """将邮箱转为安全的目录名：取 @ 前部分，替换非法字符"""
    local = email.split("@")[0] if "@" in email else email
    for ch in r'<>:"/\|?*':
        local = local.replace(ch, "_")
    return local.strip() or "user"


def get_user_dir(email: str) -> str:
    """获取用户文件目录的绝对路径"""
    return os.path.join(os.path.abspath(config.FilesPath), _sanitize_dir_name(email))


def create_user_dir(email: str) -> str:
    """创建用户文件目录"""
    user_dir = get_user_dir(email)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def remove_user_dir(email: str) -> None:
    """删除用户文件目录"""
    user_dir = get_user_dir(email)
    if os.path.exists(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)


# ==================== Token 验证 ====================

def _decode_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    """从 HTTP Bearer 凭据中解码 JWT，返回 email"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM]) 
        email = payload.get("sub")  
        if not isinstance(email, str):
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return email
    except jwt.ExpiredSignatureError: 
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError: 
        raise HTTPException(status_code=401, detail="Invalid token")


def _validate_user(email: str, check_disabled: bool = True) -> UserDict:
    """查询并校验用户是否存在及是否被禁用，返回用户字典"""
    user = store.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User '{email}' not found")
    if check_disabled and user.get("is_disable"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User '{email}' is disabled")
    return user


def verify_token_and_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # pyright: ignore[reportCallInDefaultInitializer]
) -> str:
    """验证 Token 并检查用户是否存在且未被禁用，返回 email"""
    email = _decode_token(credentials)
    _validate_user(email)  # pyright: ignore[reportUnusedCallResult]
    return email


def verify_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # pyright: ignore[reportCallInDefaultInitializer]
) -> str:
    """验证 Token 并检查用户是否为管理员，返回 email"""
    email = _decode_token(credentials)
    user = _validate_user(email)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return email