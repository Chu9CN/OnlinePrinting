"""
使用 pywin32 调用 Word 和 Excel 打印 Office 文件
通过 win32print API 设置打印机属性（方向、双面、纸张、色彩等）
支持 .doc, .docx, .xls, .xlsx 格式
"""
from __future__ import annotations
# pyright: reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false
# pyright: reportMissingTypeArgument=false, reportCallIssue=false
# pyright: reportArgumentType=false, reportMissingParameterType=false
# pyright: reportUnusedParameter=false, reportUnusedCallResult=false
# pywin32 / win32com 类型桩不完整，以上规则为已知假阳性

import os
import time
import pythoncom
import win32print
import win32com.client

# 支持的文件类型
WORD_EXTENSIONS = {".doc", ".docx"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}

# 纸张大小映射（名称 -> win32print 纸张编号）
# 常见纸张编号参考 Windows DEVMODE dmPaperSize
PAPER_SIZE_MAP = {
    "A3": 8,
    "A4": 9,
    "A5": 11,
    "B4": 12,
    "B5": 13,
    "Letter": 1,
    "Legal": 5,
}

# 双面模式映射 -> DEVMODE dmDuplex 值
DUPLEX_MAP = {
    "duplex": 2,       # DMDUP_VERTICAL (长边翻转)
    "duplexlong": 2,   # DMDUP_VERTICAL
    "duplexshort": 3,  # DMDUP_HORIZONTAL (短边翻转)
}


def _get_printer_devmode(printer_name: str) -> tuple:
    """
    获取打印机的 DEVMODE 和 PRINTER_INFO_2
    返回 (devmode, printer_handle)
    """
    try:
        # PRINTER_ALL_ACCESS = 0x000F000C
        handle = win32print.OpenPrinter(printer_name)
        # 获取 PRINTER_INFO_2 获取默认 DEVMODE
        level = 2
        printer_info = win32print.GetPrinter(handle, level)
        # pDevMode 在 PRINTER_INFO_2 的索引 7
        devmode = printer_info["pDevMode"]
        return devmode, handle
    except Exception:
        return None, None


def _set_devmode_properties(devmode, printer_name: str, orientation: str | None = None,
                             duplex: str | None = None, paper_size: str | None = None,
                             color_mode: str | None = None, paper_tray: int | None = None):
    """
    通过 win32print 的 DocumentProperties 修改打印机 DEVMODE 属性

    参考 DEVMODE 结构体字段:
      - dmOrientation: 1=纵向, 2=横向
      - dmDuplex: 1=单面, 2=双面长边, 3=双面短边
      - dmPaperSize: 纸张编号 (DMPAPER_A4=9 等)
      - dmColor: 1=单色, 2=彩色
      - dmDefaultSource: 进纸托盘编号
    """
    if not devmode:
        return devmode

    changed = False

    # 纸张方向: dmOrientation (索引偏移 44，但用 pywin32 的属性名更安全)
    if orientation:
        orient_val = 2 if orientation == "landscape" else 1
        if devmode.Orientation != orient_val:
            devmode.Orientation = orient_val
            changed = True

    # 双面打印: dmDuplex
    if duplex:
        duplex_val = DUPLEX_MAP.get(duplex, 1)
        if devmode.Duplex != duplex_val:
            devmode.Duplex = duplex_val
            changed = True
    elif duplex == "":
        # 显式传空字符串 = 单面
        if devmode.Duplex != 1:
            devmode.Duplex = 1
            changed = True

    # 纸张大小: dmPaperSize
    if paper_size and paper_size in PAPER_SIZE_MAP:
        paper_val = PAPER_SIZE_MAP[paper_size]
        if devmode.PaperSize != paper_val:
            devmode.PaperSize = paper_val
            changed = True

    # 色彩模式: dmColor
    if color_mode:
        color_val = 1 if color_mode == "monochrome" else 2
        if devmode.Color != color_val:
            devmode.Color = color_val
            changed = True

    # 进纸托盘: dmDefaultSource
    if paper_tray is not None and paper_tray >= 0:
        if devmode.DefaultSource != paper_tray:
            devmode.DefaultSource = paper_tray
            changed = True

    if changed:
        # 通过 DocumentProperties 将修改应用到打印机
        try:
            # DM_IN_BUFFER = 8, DM_OUT_BUFFER = 2
            win32print.DocumentProperties(
                0, printer_name, devmode, devmode, 8 | 2
            )
        except Exception:
            pass

    return devmode


def _apply_printer_settings(printer_name: str, orientation: str | None = None,
                            duplex: str | None = None, paper_size: str | None = None,
                            color_mode: str | None = None, paper_tray: int | None = None):
    """
    通过 win32print API 修改指定打印机的默认 DEVMODE 属性。
    这样后续 Word/Excel 使用 ActivePrinter 时就会继承这些设置。
    """
    devmode, handle = _get_printer_devmode(printer_name)
    if devmode and handle:
        try:
            _set_devmode_properties(
                devmode, printer_name,
                orientation=orientation,
                duplex=duplex,
                paper_size=paper_size,
                color_mode=color_mode,
                paper_tray=paper_tray,
            )
        finally:
            win32print.ClosePrinter(handle)


def print_word(file_path: str, printer: str | None = None, copies: int = 1,
               page_from: int | None = None, page_to: int | None = None,
               orientation: str | None = None, duplex: str | None = None,
               paper_size: str | None = None, color_mode: str | None = None,
               paper_tray: int | None = None):
    """
    使用 Word 打印文档

    Args:
        file_path: 文件路径
        printer: 打印机名称，None 使用默认打印机
        copies: 打印份数
        page_from: 起始页码（1-based）
        page_to: 结束页码（1-based）
        orientation: "portrait" 或 "landscape"
        duplex: "duplex" / "duplexlong" / "duplexshort"
        paper_size: 如 "A4", "Letter"
        color_mode: "color" 或 "monochrome"
        paper_tray: 进纸托盘编号
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        # 先通过 win32print 设置打印机属性
        if printer and any([orientation, duplex, paper_size, color_mode,
                            paper_tray is not None]):
            _apply_printer_settings(
                printer,
                orientation=orientation,
                duplex=duplex,
                paper_size=paper_size,
                color_mode=color_mode,
                paper_tray=paper_tray,
            )

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # 不弹出保存修改提示

        doc = word.Documents.Open(file_path)

        # 设置活动打印机
        if printer:
            word.ActivePrinter = printer

        # 构建 PrintOut 参数
        kwargs = {
            "Copies": max(copies, 1),
            "Background": True,  # 后台打印
        }

        if page_from is not None and page_to is not None:
            kwargs["Range"] = 2       # 2 = wdPrintRangeOfPages
            kwargs["From"] = str(page_from)
            kwargs["To"] = str(page_to)

        # Word 也支持直接传这些参数到 PrintOut
        if orientation:
            # Word 文档页面方向通过 PageSetup 设置
            try:
                if orientation == "landscape":
                    doc.PageSetup.Orientation = 1  # wdOrientLandscape
                else:
                    doc.PageSetup.Orientation = 0  # wdOrientPortrait
            except Exception:
                pass

        doc.PrintOut(**kwargs)
        return True
    finally:
        if doc:
            doc.Close(SaveChanges=False)
        if word:
            word.Quit()
        pythoncom.CoUninitialize()


def print_excel(file_path: str, printer: str | None = None, copies: int = 1,
                page_from: int | None = None, page_to: int | None = None,
                orientation: str | None = None, duplex: str | None = None,
                paper_size: str | None = None, color_mode: str | None = None,
                paper_tray: int | None = None):
    """
    使用 Excel 打印工作簿

    Args:
        file_path: 文件路径
        printer: 打印机名称，None 使用默认打印机
        copies: 打印份数
        page_from: 起始页码（1-based）
        page_to: 结束页码（1-based）
        orientation: "portrait" 或 "landscape"
        duplex: "duplex" / "duplexlong" / "duplexshort"
        paper_size: 如 "A4", "Letter"
        color_mode: "color" 或 "monochrome"
        paper_tray: 进纸托盘编号
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        # 关闭屏幕更新和警告
        excel.ScreenUpdating = False
        excel.EnableEvents = False

        wb = excel.Workbooks.Open(file_path)

        # 确定目标打印机名称
        if printer:
            target_printer = printer
        else:
            # 获取 Excel 当前活动打印机
            try:
                active = excel.ActivePrinter
                if " on " in active:
                    target_printer = active.split(" on ")[0]
                else:
                    target_printer = active
            except Exception:
                target_printer = ""

        # 设置活动打印机
        # Excel 的 ActivePrinter 需要 "PrinterName on PortName" 完整格式
        if printer:
            # 从 win32print 获取打印机端口信息，构造完整名称
            active_printer_str = printer
            try:
                handle = win32print.OpenPrinter(printer)
                info = win32print.GetPrinter(handle, 2)
                win32print.ClosePrinter(handle)
                port = info.get("pPortName", "")
                if port:
                    active_printer_str = f"{printer} on {port}"
            except Exception:
                pass

            try:
                excel.ActivePrinter = active_printer_str
            except Exception:
                # 仍然失败则使用 Excel 默认打印机
                pass

        # Excel 页面设置（应用到所有工作表）
        if orientation:
            orient_val = 2 if orientation == "landscape" else 1  # xlLandscape=2, xlPortrait=1
            for ws in wb.Worksheets:
                try:
                    ws.PageSetup.Orientation = orient_val
                except Exception:
                    pass

        if paper_size:
            paper_val = PAPER_SIZE_MAP.get(paper_size)
            if paper_val is not None:
                for ws in wb.Worksheets:
                    try:
                        ws.PageSetup.PaperSize = paper_val
                    except Exception:
                        pass

        # 构建 PrintOut 参数
        kwargs = {
            "Copies": max(copies, 1),
        }

        if page_from is not None and page_to is not None:
            kwargs["From"] = page_from
            kwargs["To"] = page_to

        # 记录打印前目标打印机的作业数
        jobs_before = 0
        if target_printer:
            try:
                handle = win32print.OpenPrinter(target_printer)
                jobs_before = len(win32print.EnumJobs(handle, 0, -1, 1))
                win32print.ClosePrinter(handle)
            except Exception:
                pass

        # 打印
        wb.PrintOut(**kwargs)

        # 等待打印作业进入 Windows 打印队列（Excel 的 PrintOut 是异步的）
        if target_printer:
            for _ in range(30):
                time.sleep(1)
                try:
                    handle = win32print.OpenPrinter(target_printer)
                    current_jobs = win32print.EnumJobs(handle, 0, -1, 1)
                    win32print.ClosePrinter(handle)
                    if len(current_jobs) > jobs_before:
                        break
                except Exception:
                    time.sleep(1)
        else:
            # 如果无法确定打印机，至少等待一段时间
            time.sleep(5)

        return True
    finally:
        if wb:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
        if excel:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def print_office_file(file_path: str, printer: str | None = None, copies: int = 1,
                      page_from: int | None = None, page_to: int | None = None,
                      orientation: str | None = None, duplex: str | None = None,
                      paper_size: str | None = None, color_mode: str | None = None,
                      paper_tray: int | None = None):
    """
    根据文件扩展名自动选择 Word 或 Excel 打印

    Args:
        file_path: 文件路径
        printer: 打印机名称，None 使用默认打印机
        copies: 打印份数
        page_from: 起始页码
        page_to: 结束页码
        orientation: "portrait" 或 "landscape"
        duplex: "duplex" / "duplexlong" / "duplexshort"
        paper_size: 如 "A4", "Letter"
        color_mode: "color" 或 "monochrome"
        paper_tray: 进纸托盘编号

    Returns:
        bool: 打印是否成功
    """
    ext = os.path.splitext(file_path)[1].lower()

    common_kwargs = dict(
        printer=printer, copies=copies,
        page_from=page_from, page_to=page_to,
        orientation=orientation, duplex=duplex,
        paper_size=paper_size, color_mode=color_mode,
        paper_tray=paper_tray,
    )

    if ext in WORD_EXTENSIONS:
        return print_word(file_path, **common_kwargs)
    elif ext in EXCEL_EXTENSIONS:
        return print_excel(file_path, **common_kwargs)
    else:
        raise ValueError(f"不支持的文件类型: {ext}，仅支持 {WORD_EXTENSIONS | EXCEL_EXTENSIONS}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python print_office.py <文件路径> [打印机名称] [份数] [起始页] [结束页]")
        print("示例: python print_office.py C:\\test\\demo.docx")
        print("示例: python print_office.py C:\\test\\demo.xlsx \"HP Printer\" 2 1 5")
        sys.exit(1)

    file_path = sys.argv[1]
    printer = sys.argv[2] if len(sys.argv) > 2 else None
    copies = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    page_from = int(sys.argv[4]) if len(sys.argv) > 4 else None
    page_to = int(sys.argv[5]) if len(sys.argv) > 5 else None

    try:
        print(f"正在打印: {file_path}")
        print_office_file(file_path, printer, copies, page_from, page_to)
        print("打印成功")
    except Exception as e:
        print(f"打印失败: {e}")
        sys.exit(1)
