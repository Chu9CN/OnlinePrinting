# 转PDF API
import os
import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.store import get_user_by_email
from core.utils import verify_token_and_user, get_user_dir
from core.logger import write_log
from office.topdf import convert_to_pdf as _do_convert

topdf_router = APIRouter(prefix="/api/topdf", tags=["转PDF"])

# 支持的文件类型
SUPPORTED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx"}


def _resolve_file_path(email: str, filename: str) -> str:
    """根据邮箱和文件名解析安全的文件绝对路径"""
    if not get_user_by_email(email):
        raise HTTPException(status_code=401, detail="用户不存在")
    user_dir = get_user_dir(email)
    safe = filename.replace("\\", "/").lstrip("/")
    if ".." in safe.split("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    target = os.path.normpath(os.path.join(user_dir, safe))
    if not os.path.abspath(target).startswith(os.path.abspath(user_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _convert_worker(email: str, file_path: str, filename: str):
    """后台线程：执行文件转换"""
    try:
        output_pdf_path = os.path.splitext(file_path)[0] + ".pdf"
        _do_convert(file_path, output_pdf_path)
        write_log(email, f"转PDF: {filename}", "成功", f"已转换为 PDF")
    except Exception as e:
        write_log(email, f"转PDF: {filename}", "失败", str(e))


# ==================== 转PDF请求 ====================

class ToPdfRequest(BaseModel):
    filenames: List[str]  # 需要转换的文件名列表


class ToPdfResult(BaseModel):
    original: str      # 原文件名
    pdf_name: str      # 生成的PDF文件名
    success: bool
    message: str


class ToPdfResponse(BaseModel):
    results: List[ToPdfResult]


@topdf_router.post("/convert", response_model=ToPdfResponse)
def convert_to_pdf(
    data: ToPdfRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """批量转换文件为PDF"""
    results = []

    for filename in data.filenames:
        try:
            file_path = _resolve_file_path(current_user, filename)
            ext = os.path.splitext(filename)[1].lower()

            if not os.path.exists(file_path):
                results.append(ToPdfResult(
                    original=filename,
                    pdf_name="",
                    success=False,
                    message="文件不存在"
                ))
                continue

            if ext not in SUPPORTED_EXTENSIONS:
                results.append(ToPdfResult(
                    original=filename,
                    pdf_name="",
                    success=False,
                    message=f"不支持的文件类型，仅支持: {', '.join(SUPPORTED_EXTENSIONS)}"
                ))
                continue

            pdf_name = os.path.splitext(os.path.basename(filename))[0] + ".pdf"
            # 保留子目录结构
            subdir = os.path.dirname(filename)
            if subdir:
                pdf_name = subdir.replace("\\", "/") + "/" + pdf_name
            pdf_path = os.path.splitext(file_path)[0] + ".pdf"

            # 后台执行转换
            thread = threading.Thread(
                target=_convert_worker,
                args=(current_user, file_path, filename)
            )
            thread.daemon = True
            thread.start()

            results.append(ToPdfResult(
                original=filename,
                pdf_name=pdf_name,
                success=True,
                message="转换中..."
            ))

        except HTTPException:
            results.append(ToPdfResult(
                original=filename,
                pdf_name="",
                success=False,
                message="路径无效"
            ))
        except Exception as e:
            results.append(ToPdfResult(
                original=filename,
                pdf_name="",
                success=False,
                message=str(e)
            ))

    return ToPdfResponse(results=results)
