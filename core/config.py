import os
import sys


def get_app_dir() -> str:
    """获取应用根目录
    开发模式: 项目根目录 (core/ 的父目录)
    打包后:   exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_APP_DIR = get_app_dir()

# ==================== 服务器 ====================
ServerHost = "0.0.0.0"
ServerPort = 8080

# ==================== 安全 ====================
SecretKey = "BfUgFBU6IckVTtkafghmFCtaD5eGmI3r"  # 生产环境请务必修改为随机字符串

# ==================== 路径 ====================
FilesPath  = os.path.join(_APP_DIR, "files")
SumatraPDF = os.path.join(_APP_DIR, "./office/SumatraPDF.exe")

# ==================== 清理 ====================
Retention_Days = 30

