"""
文件清理任务 - 每天凌晨 4 点删除超过 30 天的用户文件
"""
import os
import time
import threading
from datetime import datetime, timedelta

from core import config
from core.logger import write_log


def _get_retention_days() -> int:
    """从配置读取保留天数，默认 30 天"""
    try:
        return int(config.Retention_Days)
    except (ValueError, AttributeError):
        return 30


def _clean_old_files():
    """清理所有用户目录中超过配置天数的文件"""
    retention_days = _get_retention_days()
    base = os.path.abspath(config.FilesPath)
    if not os.path.exists(base):
        return

    now = time.time()
    cutoff = now - retention_days * 24 * 3600
    deleted_count = 0

    for user_dir_name in os.listdir(base):
        user_dir = os.path.join(base, user_dir_name)
        if not os.path.isdir(user_dir):
            continue

        # 遍历用户目录下的所有文件和子目录
        for root, dirs, files in os.walk(user_dir, topdown=False):
            for name in files:
                file_path = os.path.join(root, name)
                try:
                    mtime = os.path.getmtime(file_path)
                    if mtime < cutoff:
                        os.remove(file_path)
                        deleted_count += 1
                except Exception:
                    pass

            # 删除空的子目录
            for name in dirs:
                dir_path = os.path.join(root, name)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

    if deleted_count > 0:
        write_log("系统", f"定时清理过期文件", "成功", f"删除 {deleted_count} 个超过 {retention_days} 天的文件")


def _cleaner_loop():
    """后台循环：计算距离下一次凌晨 4 点的秒数，到时执行清理"""
    while True:
        now = datetime.now()
        # 计算今天凌晨 4 点
        target = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if now >= target:
            # 已过今天 4 点，取明天 4 点
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        time.sleep(wait_seconds)
        _clean_old_files()


def start_cleaner():
    """启动文件清理后台线程（守护线程）"""
    t = threading.Thread(target=_cleaner_loop, daemon=True)
    t.start()
