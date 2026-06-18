"""
日志记录工具 — 记录用户操作日志到 JSON 存储
"""


from core.store import add_log


def write_log(username: str, action: str, result: str = "成功", detail: str | None = None) -> None:
    """写入一条操作日志（JSON 存储）"""
    add_log(username, action, result, detail)
