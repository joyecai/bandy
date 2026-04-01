#!/usr/bin/env python3
"""Bandy Dashboard - 独立常驻面板服务

启动方式: python serve.py
面板地址: http://localhost:<yaml 中 dashboard.port>
通过面板上的按钮启动/停止 Bandy 语音助手
"""
import os
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import asyncio
import signal
import subprocess
import warnings
import logging

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")


def _kill_port(port: int):
    """启动前强制释放端口"""
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], text=True).strip()
        for pid in out.split():
            pid = pid.strip()
            if pid and pid != str(os.getpid()):
                os.kill(int(pid), 9)
                print(f"🧹 已终止占用端口 {port} 的进程 (PID {pid})", flush=True)
    except (subprocess.CalledProcessError, OSError):
        pass


async def main():
    from bandy.config import cfg
    from bandy.dashboard import start_dashboard

    port = cfg.DASHBOARD_PORT
    _kill_port(port)

    await asyncio.sleep(0.5)

    runner = await start_dashboard(port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
