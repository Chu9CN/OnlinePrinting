# api/printfile.py
import os
import subprocess
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import win32print

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.store import get_user_by_email
from core.utils import verify_token_and_user, get_user_dir
from core.logger import write_log
from office.print_office import print_office_file, WORD_EXTENSIONS, EXCEL_EXTENSIONS

print_router = APIRouter(prefix="/api/print", tags=["打印"])

# SumatraPDF 路径（来自 config.py 配置）
from core.config import SumatraPDF as SUMATRAPDF

# 需要排除的打印机
EXCLUDED_PRINTERS = ["Microsoft Print to PDF", "OneNote (Desktop)", "OneNote"]

# 支持的 Office 文件扩展名
OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS


# ==================== 打印队列 ====================

_print_queue: deque = deque()
_queue_lock = threading.Lock()
_next_task_id = 0
_task_id_lock = threading.Lock()


def _build_print_settings(task: dict) -> str:
    """根据任务参数构建 SumatraPDF -print-settings 字符串"""
    settings = []

    # 纸张方向
    orientation = task.get("orientation") or "portrait"
    settings.append(orientation)

    # 双面打印
    duplex = task.get("duplex")
    if duplex:
        if duplex == "duplexlong":
            settings.append("duplexlong")
        elif duplex == "duplexshort":
            settings.append("duplexshort")
        else:
            settings.append("duplex")
    else:
        settings.append("simplex")

    # 色彩模式
    color_mode = task.get("color_mode") or "color"
    settings.append(color_mode)

    # 缩放模式
    scale_mode = task.get("scale_mode") or "fit"
    if scale_mode:
        settings.append(scale_mode)

    # 纸张大小
    paper_size = task.get("paper_size")
    if paper_size:
        settings.append(f"paper={paper_size}")

    # 纸张托盘
    paper_tray = task.get("paper_tray")
    if paper_tray is not None:
        try:
            tray_num = int(paper_tray)
            if tray_num >= 0:
                settings.append(f"bin={tray_num}")
        except (ValueError, TypeError):
            pass

    # 页面布局
    page_layout = task.get("page_layout") or "1x"
    if page_layout and page_layout != "1x":
        settings.append(page_layout)

    return ",".join(settings)


def _is_office_file(file_path: str) -> bool:
    """判断文件是否为 Office 文件（Word 或 Excel）"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in OFFICE_EXTENSIONS


def _parse_page_range(page_range: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """解析页码范围字符串，返回 (from_page, to_page)
    
    支持格式: "3" (单页), "2-5" (范围), "1,3,5" (逗号分隔取首尾)
    """
    if not page_range:
        return None, None
    page_range = page_range.strip()
    if not page_range:
        return None, None
    try:
        # 处理逗号分隔: 取最小和最大页码
        parts = page_range.replace(",", " ").split()
        pages = []
        for part in parts:
            if "-" in part:
                a, b = part.split("-", 1)
                pages.extend([int(a), int(b)])
            else:
                pages.append(int(part))
        if pages:
            return min(pages), max(pages)
    except (ValueError, TypeError):
        pass
    return None, None


def _print_worker():
    """后台线程：串行消费打印队列"""
    while True:
        task = None
        with _queue_lock:
            if _print_queue:
                task = _print_queue[0]
        if task is None:
            time.sleep(0.5)
            continue

        file_path = task["file_path"]
        task["status"] = "printing"
        try:
            copies = max(task.get("copies", 1), 1)
            page_range = task.get("page_range")
            printer = task.get("printer")

            if _is_office_file(file_path):
                # ========== Office 文件打印 (win32print 参数) ==========
                page_from, page_to = _parse_page_range(page_range)

                print_office_file(
                    file_path=file_path,
                    printer=printer,
                    copies=copies,
                    page_from=page_from,
                    page_to=page_to,
                    orientation=task.get("orientation"),
                    duplex=task.get("duplex"),
                    paper_size=task.get("paper_size"),
                    color_mode=task.get("color_mode"),
                    paper_tray=task.get("paper_tray"),
                )
            else:
                # ========== PDF 文件打印 (SumatraPDF) ==========
                # 构建打印设置
                print_settings = _build_print_settings(task)

                # SumatraPDF 命令:
                base_cmd = [SUMATRAPDF]
                if printer:
                    base_cmd.extend(["-print-to", printer])
                else:
                    base_cmd.append("-print-to-default")
                base_cmd.extend(["-print-settings", print_settings])
                if page_range:
                    base_cmd.extend(["-print-page-range", page_range])
                base_cmd.append("-exit-on-print")

                # 隐藏窗口
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                for _ in range(copies):
                    cmd = base_cmd + [file_path]
                    subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120,
                        startupinfo=startupinfo,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )

            task["status"] = "done"
            filename = os.path.basename(file_path)
            printer_name = printer or "默认打印机"
            duplex_label = "双面" if task.get("duplex") else "单面"
            range_info = f", 页码: {page_range}" if page_range else ""
            orient_info = f", 方向: {task.get('orientation', 'portrait')}" if task.get("orientation") else ""
            paper_info = f", 纸张: {task.get('paper_size')}" if task.get("paper_size") else ""
            write_log(task["username"], f"打印文件: {filename}", "成功",
                      f"打印机: {printer_name}, {copies}份, {duplex_label}{range_info}{orient_info}{paper_info}")
        except Exception as e:
            task["status"] = "failed"
            filename = os.path.basename(file_path)
            write_log(task["username"], f"打印文件: {filename}", "失败", str(e))

        with _queue_lock:
            if _print_queue and _print_queue[0]["task_id"] == task["task_id"]:
                _print_queue.popleft()


_worker_thread = threading.Thread(target=_print_worker, daemon=True)
_worker_thread.start()


def _resolve_file_path(email: str, filename: str) -> str:
    """根据邮箱和文件名解析安全的文件绝对路径"""
    if not get_user_by_email(email):
        raise HTTPException(status_code=401, detail="用户不存在")
    user_dir = get_user_dir(email)
    target = os.path.normpath(os.path.join(user_dir, filename))
    if not os.path.abspath(target).startswith(os.path.abspath(user_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


def _get_printer_status(printer_name: str) -> Tuple[str, bool]:
    """获取打印机状态，返回 (状态描述, 是否可用)"""
    try:
        handle = win32print.OpenPrinter(printer_name)
        info = win32print.GetPrinter(handle, 2)
        win32print.ClosePrinter(handle)
        status = info.get("Status", 0)
        if status == 0:
            return "就绪", True
        if status & 0x80:   # PRINTER_STATUS_OFFLINE
            return "脱机", False
        if status & 0x01:   # PRINTER_STATUS_PAUSED
            return "已暂停", False
        if status & 0x02:   # PRINTER_STATUS_ERROR
            return "错误", False
        if status & 0x10:   # PRINTER_STATUS_PAPER_OUT
            return "缺纸", False
        if status & 0x100:  # PRINTER_STATUS_TONER_LOW
            return "碳粉不足", True
        return "就绪", True
    except Exception:
        return "未知", False


def _get_printers() -> List[dict]:
    """通过 pywin32 获取系统打印机列表，排除虚拟打印机，含状态信息"""
    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags, None, 1)
        default = _get_default_printer()
        result = []
        for p in printers:
            name = p[2]
            if not name or any(ex.lower() in name.lower() for ex in EXCLUDED_PRINTERS):
                continue
            status_text, is_available = _get_printer_status(name)
            result.append({
                "name": name,
                "is_default": name == default,
                "status": status_text,
                "is_available": is_available,
            })
        return result
    except Exception:
        return []


def _get_default_printer() -> str:
    """通过 pywin32 获取系统默认打印机"""
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


# ==================== 打印机列表 ====================

class PrinterInfo(BaseModel):
    name: str
    is_default: bool
    status: str = "就绪"
    is_available: bool = True


@print_router.get("/printers", response_model=List[PrinterInfo])
def list_printers(current_user: str = Depends(verify_token_and_user)):
    """获取可用打印机列表（含状态信息）"""
    printers = _get_printers()
    return [PrinterInfo(**p) for p in printers]


# ==================== 队列状态 ====================

class QueueStatus(BaseModel):
    queue_length: int
    position: Optional[int] = None
    current_printing: bool = False


@print_router.get("/queue-status", response_model=QueueStatus)
def queue_status(current_user: str = Depends(verify_token_and_user)):
    """查看当前打印队列状态（仅暴露数量，不泄露文件名）"""
    with _queue_lock:
        total = len(_print_queue)
        current_printing = total > 0 and _print_queue[0]["status"] == "printing"
        pos = next((i + 1 for i, t in enumerate(_print_queue) if t["username"] == current_user), None)

    return QueueStatus(queue_length=total, position=pos, current_printing=current_printing)


# ==================== 提交打印任务（入队） ====================

class PrintRequest(BaseModel):
    filename: str
    printer: Optional[str] = None
    copies: int = 1
    duplex: Optional[str] = None  # "duplex", "duplexlong", "duplexshort"；为空表示单面
    page_range: Optional[str] = None  # 如 "3" 或 "2-5"
    orientation: Optional[str] = None  # "portrait" 或 "landscape"
    color_mode: Optional[str] = None  # "color" 或 "monochrome"
    scale_mode: Optional[str] = None  # "noscale", "shrink", "fit"
    paper_size: Optional[str] = None  # 如 "A4", "Letter"
    paper_tray: Optional[int] = None  # 进纸托盘编号
    page_layout: Optional[str] = None  # "1x", "book", "booklet"


class PrintTaskResponse(BaseModel):
    task_id: int
    queue_position: int


@print_router.post("/file", response_model=PrintTaskResponse)
def print_file(
    data: PrintRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """提交单个打印任务到队列"""
    file_path = _resolve_file_path(current_user, data.filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    global _next_task_id
    with _task_id_lock:
        _next_task_id += 1
        task_id = _next_task_id

    task = {
        "task_id": task_id, "username": current_user,
        "file_path": file_path, "printer": data.printer,
        "copies": data.copies, "duplex": data.duplex,
        "page_range": data.page_range,
        "orientation": data.orientation,
        "color_mode": data.color_mode,
        "scale_mode": data.scale_mode,
        "paper_size": data.paper_size,
        "paper_tray": data.paper_tray,
        "page_layout": data.page_layout,
        "status": "queued",
    }

    with _queue_lock:
        _print_queue.append(task)
        position = len(_print_queue)

    return PrintTaskResponse(task_id=task_id, queue_position=position)


# ==================== 批量提交打印任务 ====================

class BatchPrintRequest(BaseModel):
    filenames: List[str]
    printer: Optional[str] = None
    copies: int = 1
    duplex: Optional[str] = None  # "duplex", "duplexlong", "duplexshort"；为空表示单面
    page_range: Optional[str] = None
    orientation: Optional[str] = None
    color_mode: Optional[str] = None
    scale_mode: Optional[str] = None
    paper_size: Optional[str] = None
    paper_tray: Optional[int] = None
    page_layout: Optional[str] = None


class BatchPrintTaskResponse(BaseModel):
    tasks: List[PrintTaskResponse]


@print_router.post("/batch", response_model=BatchPrintTaskResponse)
def batch_print(
    data: BatchPrintRequest,
    current_user: str = Depends(verify_token_and_user),
):
    """批量提交打印任务到队列"""
    global _next_task_id
    tasks = []

    for filename in data.filenames:
        try:
            file_path = _resolve_file_path(current_user, filename)
            if not os.path.exists(file_path):
                tasks.append(PrintTaskResponse(task_id=0, queue_position=-1))
                continue

            with _task_id_lock:
                _next_task_id += 1
                task_id = _next_task_id

            task = {
                "task_id": task_id, "username": current_user,
                "file_path": file_path, "printer": data.printer,
                "copies": data.copies, "duplex": data.duplex,
                "page_range": data.page_range,
                "orientation": data.orientation,
                "color_mode": data.color_mode,
                "scale_mode": data.scale_mode,
                "paper_size": data.paper_size,
                "paper_tray": data.paper_tray,
                "page_layout": data.page_layout,
                "status": "queued",
            }

            with _queue_lock:
                _print_queue.append(task)
                position = len(_print_queue)

            tasks.append(PrintTaskResponse(task_id=task_id, queue_position=position))
        except HTTPException:
            tasks.append(PrintTaskResponse(task_id=0, queue_position=-1))

    return BatchPrintTaskResponse(tasks=tasks)
