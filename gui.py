"""
OnlinePrinting - Windows 启动界面
使用 win32gui 构建原生 Windows GUI 控制面板

三种状态：
  默认 ── 未启动，指示灯灰色
  运行 ── 绿色指示灯，"停止服务"按钮可用
  停止 ── 红色指示灯，"启动服务"按钮可用
"""
from __future__ import annotations
# pyright: reportMissingModuleSource=false, reportAttributeAccessIssue=false, reportArgumentType=false
# pyright: reportReturnType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnnecessaryTypeIgnoreComment=false, reportUnusedCallResult=false
# pyright: reportUnknownVariableType=false, reportPossiblyUnboundVariable=false
# pyright: reportCallIssue=false
# pywin32 类型桩不完整，以上规则对 win32 API 调用为已知假阳性

import asyncio
import contextlib
import os
import sys
import threading
from dataclasses import dataclass
from enum import Enum, auto

import win32gui  
import win32api 
import win32con 
import uvicorn

# Windows 上避免 ProactorEventLoop 导致的关闭异常
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ==================== 打包路径适配 ====================

def _get_app_dir() -> str:
    """获取应用根目录"""
    from core.config import get_app_dir  # pyright: ignore[reportUnusedImport]
    return get_app_dir()


# ==================== 颜色常量 ====================
RGB = win32api.RGB
COLOR_BG          = RGB(240, 242, 245)
COLOR_PANEL_BG    = RGB(255, 255, 255)
COLOR_TEXT        = RGB(51, 51, 51)
COLOR_TEXT_SECOND = RGB(140, 150, 165)
COLOR_GRAY        = RGB(180, 185, 195)
COLOR_GREEN       = RGB(46, 204, 113)
COLOR_RED         = RGB(231, 76, 60)
COLOR_BLUE        = RGB(52, 152, 219)
COLOR_BORDER      = RGB(220, 223, 230)
COLOR_BTN_BG      = RGB(245, 247, 250)


class State(Enum):
    DEFAULT = auto()   # 未启动 —— 灰色
    RUNNING = auto()   # 运行中 —— 绿色
    STOPPED = auto()   # 已停止 —— 红色


@dataclass
class Rect:
    left: int; top: int; right: int; bottom: int

    @property
    def width(self) -> int: return self.right - self.left
    @property
    def height(self) -> int: return self.bottom - self.top


# ==================== 全局状态 ====================
WINDOW_WIDTH, WINDOW_HEIGHT = 480, 360
BUTTON_WIDTH, BUTTON_HEIGHT = 160, 44
STATUS_CIRCLE_R = 40
STATUS_CIRCLE_Y = 120

g_state = State.DEFAULT
g_server: uvicorn.Server | None = None
g_server_thread: threading.Thread | None = None


def create_solid_brush(color: int) -> int:
    return win32gui.CreateSolidBrush(color)  # pyright: ignore[reportUnknownMemberType]


def draw_rounded_rect(hdc: int, rect: Rect, radius: int, color: int) -> None:
    """绘制圆角矩形"""
    brush = create_solid_brush(color)
    pen = win32gui.CreatePen(win32con.PS_SOLID, 0, color)  # pyright: ignore[reportUnknownMemberType]
    old_brush = win32gui.SelectObject(hdc, brush)
    old_pen = win32gui.SelectObject(hdc, pen)
    win32gui.RoundRect(hdc, rect.left, rect.top, rect.right, rect.bottom, radius, radius)  # pyright: ignore[reportUnknownMemberType]
    win32gui.SelectObject(hdc, old_brush)
    win32gui.SelectObject(hdc, old_pen)
    win32gui.DeleteObject(brush)
    win32gui.DeleteObject(pen)


def draw_centered_text(hdc: int, rect: Rect, text: str, color: int, font: int | None = None) -> None:
    """在矩形区域内居中绘制文字"""
    win32gui.SetTextColor(hdc, color)  # pyright: ignore[reportUnknownMemberType]
    win32gui.SetBkMode(hdc, win32con.TRANSPARENT)  # pyright: ignore[reportUnknownMemberType]
    old_font = win32gui.SelectObject(hdc, font) if font else None
    r = (rect.left, rect.top, rect.right, rect.bottom)
    win32gui.DrawText(hdc, text, -1, r,  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
                      win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE)
    if old_font is not None:
        win32gui.SelectObject(hdc, old_font)


def get_state_color(state: State) -> int:
    if state == State.RUNNING:
        return COLOR_GREEN
    elif state == State.STOPPED:
        return COLOR_RED
    return COLOR_GRAY


def get_state_text(state: State) -> str:
    if state == State.RUNNING:
        return "● 服务运行中"
    elif state == State.STOPPED:
        return "● 服务已停止"
    return "● 服务未启动"


def draw_status_indicator(hdc: int, x: int, y: int, state: State) -> None:
    """绘制状态指示灯（大圆点）"""
    color = get_state_color(state)
    # 光晕
    glow_brush = create_solid_brush(RGB(
        min(color & 0xFF + 60, 255),
        min((color >> 8) & 0xFF + 60, 255),
        min((color >> 16) & 0xFF + 60, 255),
    ))
    win32gui.SelectObject(hdc, glow_brush)
    win32gui.Ellipse(hdc, x - STATUS_CIRCLE_R - 4, y - STATUS_CIRCLE_R - 4,  # pyright: ignore[reportUnknownMemberType]
                     x + STATUS_CIRCLE_R + 4, y + STATUS_CIRCLE_R + 4)
    # 实心圆
    brush = create_solid_brush(color)
    win32gui.SelectObject(hdc, brush)
    win32gui.Ellipse(hdc, x - STATUS_CIRCLE_R, y - STATUS_CIRCLE_R,  # pyright: ignore[reportUnknownMemberType]
                     x + STATUS_CIRCLE_R, y + STATUS_CIRCLE_R)
    win32gui.DeleteObject(glow_brush)
    win32gui.DeleteObject(brush)


def draw_button(hdc: int, rect: Rect, text: str, enabled: bool, accent: int | None = None) -> None:
    """绘制自定义按钮"""
    if enabled and accent:
        bg = accent
        txt_color = RGB(255, 255, 255)
    elif enabled:
        bg = COLOR_BTN_BG
        txt_color = COLOR_TEXT
    else:
        bg = RGB(235, 238, 242)
        txt_color = COLOR_TEXT_SECOND

    # 边框 + 填充
    border_pen = win32gui.CreatePen(win32con.PS_SOLID, 1, COLOR_BORDER if not accent else accent)  # pyright: ignore[reportUnknownMemberType]
    win32gui.SelectObject(hdc, border_pen)
    brush = create_solid_brush(bg)
    win32gui.SelectObject(hdc, brush)
    win32gui.RoundRect(hdc, rect.left, rect.top, rect.right, rect.bottom, 10, 10)  # pyright: ignore[reportUnknownMemberType]
    win32gui.DeleteObject(border_pen)
    win32gui.DeleteObject(brush)

    # 文字
    draw_centered_text(hdc, rect, text, txt_color)


# ==================== 服务控制 ====================

def start_server() -> None:
    """在后台线程启动 FastAPI 服务"""
    import traceback
    import pythoncom
    import core.config as _cfg  # pyright: ignore[reportUnusedImport]

    # 后台线程初始化 COM，避免干扰 GUI 主线程的 GDI 操作
    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)

    # 预创建必要目录
    for d in (_cfg.FilesPath, os.path.join(_cfg.get_app_dir(), "data")):
        os.makedirs(d, exist_ok=True)

    # noconsole 模式下 sys.stdout/stderr 为 None，
    # uvicorn 在 Config/Server 初始化时就会设置日志处理器访问 stderr，
    # 必须在最外层提前重定向
    _needs_redirect = sys.stdout is None or sys.stderr is None
    _redirect_ctx = (
        contextlib.ExitStack()
        if not _needs_redirect
        else _make_devnull_redirect()
    )

    try:
        with _redirect_ctx:
            from main import app as _app
            config = uvicorn.Config(
                app=_app,
                host=_cfg.ServerHost,
                port=_cfg.ServerPort,
                log_level="info",
            )
            global g_server
            g_server = uvicorn.Server(config)
            g_server.run()
    except Exception:
        from datetime import datetime as _dt
        with open(os.path.join(_cfg.get_app_dir(), "server_error.log"), "a", encoding="utf-8") as f:
            f.write(f"[{_dt.now()}] Server stopped:\n")
            traceback.print_exc(file=f)
    finally:
        pythoncom.CoUninitialize()


def _make_devnull_redirect() -> contextlib.ExitStack:
    """创建一个将 stdout/stderr 重定向到 os.devnull 的上下文管理器"""
    stack = contextlib.ExitStack()
    devnull = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
    stack.enter_context(contextlib.redirect_stdout(devnull))
    stack.enter_context(contextlib.redirect_stderr(devnull))
    return stack


def stop_server() -> None:
    """停止 FastAPI 服务"""
    if g_server:
        g_server.should_exit = True


# ==================== 窗口过程 ====================

def set_state(hwnd: int, new_state: State) -> None:
    """切换状态并重绘"""
    global g_state
    g_state = new_state
    win32gui.InvalidateRect(hwnd, None, True)


def handle_start(hwnd: int) -> None:
    global g_server_thread
    if g_state == State.RUNNING:
        return
    set_state(hwnd, State.RUNNING)
    g_server_thread = threading.Thread(target=start_server, daemon=True)
    g_server_thread.start()


def handle_stop(hwnd: int) -> None:
    global g_server_thread
    if g_state != State.RUNNING:
        return
    stop_server()
    if g_server_thread and g_server_thread.is_alive():
        g_server_thread.join(timeout=3)
    set_state(hwnd, State.STOPPED)


def wnd_proc(hwnd: int, msg: int, wp: int, lp: int) -> int:  # pyright: ignore[reportMissingParameterType]
    try:
        if msg == win32con.WM_ERASEBKGND:
            return 1

        if msg == win32con.WM_PAINT:
            return _on_paint(hwnd)

        if msg == win32con.WM_LBUTTONDOWN:
            return _on_click(hwnd, lp)

        if msg == win32con.WM_DESTROY:
            stop_server()
            if g_server_thread and g_server_thread.is_alive():
                g_server_thread.join(timeout=3)
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wp, lp)
    except BaseException:
        return 0


def _on_paint(hwnd: int) -> int:
    """处理 WM_PAINT 消息"""
    hdc = win32gui.GetDC(hwnd)

    # 双缓冲
    w, h = WINDOW_WIDTH, WINDOW_HEIGHT
    mem_dc = win32gui.CreateCompatibleDC(hdc)
    mem_bmp = win32gui.CreateCompatibleBitmap(hdc, w, h)
    old_bmp = win32gui.SelectObject(mem_dc, mem_bmp)

    # 背景
    bg_brush = create_solid_brush(COLOR_BG)
    win32gui.FillRect(mem_dc, (0, 0, w, h), bg_brush)
    win32gui.DeleteObject(bg_brush)

    # 状态指示灯
    circle_x, circle_y = w // 2, STATUS_CIRCLE_Y
    draw_status_indicator(mem_dc, circle_x, circle_y, g_state)

    # 状态文字
    draw_centered_text(mem_dc,
                       Rect(0, circle_y + STATUS_CIRCLE_R + 12,
                            w, circle_y + STATUS_CIRCLE_R + 42),
                       get_state_text(g_state), COLOR_TEXT_SECOND)

    # 按钮
    btn_y = circle_y + STATUS_CIRCLE_R + 60
    btn_start_x, btn_stop_x = w // 2 - BUTTON_WIDTH - 14, w // 2 + 14

    draw_button(mem_dc,
                Rect(btn_start_x, btn_y, btn_start_x + BUTTON_WIDTH, btn_y + BUTTON_HEIGHT),
                "启动服务", g_state != State.RUNNING,
                COLOR_GREEN if g_state == State.RUNNING else None)

    draw_button(mem_dc,
                Rect(btn_stop_x, btn_y, btn_stop_x + BUTTON_WIDTH, btn_y + BUTTON_HEIGHT),
                "停止服务", g_state == State.RUNNING,
                COLOR_RED if g_state == State.STOPPED else None)

    # 底部
    draw_centered_text(mem_dc, Rect(0, h - 30, w, h),
                       "服务地址: http://127.0.0.1:8080", COLOR_TEXT_SECOND)

    # 刷新屏幕
    win32gui.BitBlt(hdc, 0, 0, w, h, mem_dc, 0, 0, win32con.SRCCOPY)
    win32gui.SelectObject(mem_dc, old_bmp)
    win32gui.DeleteObject(mem_bmp)
    win32gui.DeleteDC(mem_dc)
    win32gui.ReleaseDC(hwnd, hdc)
    return 0


def _on_click(hwnd: int, lp: int) -> int:
    """处理鼠标点击"""
    x, y = win32api.LOWORD(lp), win32api.HIWORD(lp)
    circle_y = STATUS_CIRCLE_Y
    btn_y = circle_y + STATUS_CIRCLE_R + 60
    btn_start_x, btn_stop_x = WINDOW_WIDTH // 2 - BUTTON_WIDTH - 14, WINDOW_WIDTH // 2 + 14

    if (btn_start_x <= x <= btn_start_x + BUTTON_WIDTH and
        btn_y <= y <= btn_y + BUTTON_HEIGHT):
        handle_start(hwnd)
    if (btn_stop_x <= x <= btn_stop_x + BUTTON_WIDTH and
        btn_y <= y <= btn_y + BUTTON_HEIGHT):
        handle_stop(hwnd)
    return 0


# ==================== 启动 GUI ====================

def run_gui() -> None:
    hinst = win32api.GetModuleHandle(None)  # pyright: ignore[reportUnknownMemberType]

    wc = win32gui.WNDCLASS()  # pyright: ignore[reportUnknownMemberType]
    wc.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
    wc.lpfnWndProc = wnd_proc  # pyright: ignore[reportAttributeAccessIssue]
    wc.hInstance = hinst  # pyright: ignore[reportAttributeAccessIssue]
    wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
    wc.hbrBackground = win32gui.GetStockObject(win32con.WHITE_BRUSH)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
    wc.lpszClassName = "PDFPrinterGUI"  # pyright: ignore[reportAttributeAccessIssue]

    atom = win32gui.RegisterClass(wc)  # pyright: ignore[reportUnknownMemberType]

    screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)  # pyright: ignore[reportUnknownMemberType]
    screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)  # pyright: ignore[reportUnknownMemberType]
    x = (screen_w - WINDOW_WIDTH) // 2
    y = (screen_h - WINDOW_HEIGHT) // 2

    hwnd = win32gui.CreateWindow(  # pyright: ignore[reportUnknownMemberType]
        atom, "OnlinePrinting",
        win32con.WS_OVERLAPPED | win32con.WS_CAPTION | win32con.WS_SYSMENU | win32con.WS_MINIMIZEBOX,
        x, y, WINDOW_WIDTH, WINDOW_HEIGHT, 0, 0, hinst, None
    )

    # 设置窗口图标
    icon_path = os.path.join(_get_app_dir(), "static", "favicon.ico")
    if os.path.isfile(icon_path):
        hicon = win32gui.LoadImage(0, icon_path, win32con.IMAGE_ICON, 0, 0,
                                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        if hicon:
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, hicon)
            win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, hicon)

    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)  # pyright: ignore[reportUnknownMemberType]
    win32gui.UpdateWindow(hwnd)  # pyright: ignore[reportUnknownMemberType]

    win32gui.PumpMessages()


if __name__ == "__main__":
    run_gui()
