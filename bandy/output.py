"""输出文件管理: 按日期子目录存放, 90 天自动清理"""
import os
import shutil
import datetime as dt

from .config import cfg


def cleanup_old_output():
    """删除超出 retention_days 的日期子目录."""
    base = cfg.output_path
    if not os.path.isdir(base):
        return
    cutoff = dt.date.today() - dt.timedelta(days=cfg.RETENTION_DAYS)
    removed = 0
    for name in os.listdir(base):
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        try:
            folder_date = dt.date.fromisoformat(name)
        except ValueError:
            continue
        if folder_date < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    if removed:
        print(f"🗑️ 已清理 {removed} 个过期输出目录", flush=True)
