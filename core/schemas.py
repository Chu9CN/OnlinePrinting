# 用户请求体、返回体
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

# 创建用户入参（前端提交：邮箱、显示名称、密码）
class UserCreate(BaseModel):
    email: str
    display_name: str = ""
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    create_time: datetime
    update_time: datetime
    is_disable: bool
    is_admin: bool
    force_password_change: bool = False

# 修改用户状态/信息
class UserUpdate(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = None
    is_disable: Optional[bool] = None
    is_admin: Optional[bool] = None