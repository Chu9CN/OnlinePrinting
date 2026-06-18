# -*- coding: utf-8 -*-
# pyright: reportUnusedCallResult=false
"""PyInstaller 打包脚本 — 将 OnlinePrinting 打包为目录"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

# ==================== 路径计算 ====================
ROOT = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(ROOT, "static", "favicon.ico")
ENTRY = os.path.join(ROOT, "gui.py")
VERSION_FILE = os.path.join(ROOT, "version.txt")
NAME = "OnlinePrinting"
DIST_DIR = os.path.join(ROOT, "dist", NAME)

# 前置校验关键文件存在
for check_path, desc in [(ICON, "程序图标 favicon.ico"), (VERSION_FILE, "版本信息 version.txt"), (ENTRY, "入口 gui.py")]:
    if not os.path.exists(check_path):
        print(f"错误：缺少{desc} -> {check_path}")
        sys.exit(1)

# ==================== 隐藏导入 ====================
HIDDEN_IMPORTS = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "bcrypt",
    "jwt",
    "pydantic",
    "email_validator",
    "multipart",
    "colorama",
]

# Windows add-data 分隔符 ; Linux/macOS :
SEP = ";" if sys.platform == "win32" else ":"

# ==================== 构建命令 ====================
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--clean",
    "--onedir",
    "--noconsole",
    "--name", NAME,
    f"--icon={ICON}",
    f"--version-file={VERSION_FILE}",
    "--add-data", f"{os.path.join(ROOT, 'office')}{SEP}office",
]

# 追加隐藏导入
for mod in HIDDEN_IMPORTS:
    cmd.extend(["--hidden-import", mod])

# 收集子模块
for pkg in ("api", "core", "office"):
    cmd.extend(["--collect-submodules", pkg])

cmd.append(ENTRY)

# ==================== 执行 PyInstaller ====================
print("=" * 60)
print("打包命令：")
print(" ".join(cmd))
print("=" * 60)

result = subprocess.run(cmd)
if result.returncode != 0:
    print(f"PyInstaller 打包失败，退出码：{result.returncode}")
    sys.exit(result.returncode)

# ==================== 复制静态资源与工具程序 ====================
 
static_src = os.path.join(ROOT, "static")
static_dst = os.path.join(DIST_DIR, "static")
if os.path.exists(static_dst):
    shutil.rmtree(static_dst)
shutil.copytree(static_src, static_dst)

office_out = os.path.join(DIST_DIR, "office")
os.makedirs(office_out, exist_ok=True)
sumatra_src = os.path.join(ROOT, "office", "SumatraPDF-3.6.1-64.exe")
sumatra_dst = os.path.join(office_out, "SumatraPDF.exe")
if os.path.exists(sumatra_src):
    shutil.copy2(sumatra_src, sumatra_dst)

print(f"\n打包完成，输出目录：{DIST_DIR}")