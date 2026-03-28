"""OpenClaw Agent 调用与复杂任务检测"""
import os
import re
import json
import time
import asyncio

from .config import cfg
from .utils import strip_markdown
from .telegram import send_tg_file

AGENT_KW_STRONG = {
    "整理", "汇总", "收集", "发送", "发到", "发给", "转发",
    "搜索", "搜一下", "查一下", "查找", "查询", "查一查",
    "下载", "上传", "保存", "创建", "生成", "制作",
    "excel", "pdf", "csv", "文件", "文档", "表格",
    "telegram", "tg", "微信", "邮件", "邮箱",
    "翻译", "总结", "分析", "对比", "比较",
}

AGENT_KW_WEAK = [
    "帮我", "帮忙", "写一个", "写个",
    "提醒", "定时", "最新", "最近", "近期",
    "价格", "股票", "汇率", "油价", "新闻",
    "行情", "走势", "排名", "报价", "多少钱",
    "怎么样", "哪个好", "推荐",
]

def _agent_preamble():
    return (
        f"用户 Telegram chat_id: {cfg.TG_CHAT_ID}。"
        "重要: 不要自行发送文件到Telegram，只需将文件保存到本地即可，系统会自动发送。"
        "如果任务需要发送文本消息到Telegram，可以直接使用该ID。"
    )

_FILE_RE = re.compile(
    r'(?:~/|/Users/)[\w./\-]+\.(?:csv|xlsx?|pdf|txt|json|png|jpg|doc|docx|zip)')
_OUTPUT_EXTS = (
    '.csv', '.xlsx', '.xls', '.pdf', '.txt', '.json',
    '.png', '.jpg', '.doc', '.docx', '.zip')


def needs_agent(text):
    low = text.lower()
    if any(kw in low for kw in AGENT_KW_STRONG):
        return True
    return sum(1 for kw in AGENT_KW_WEAK if kw in low) >= 2


def estimate_minutes(task, task_history):
    low = task.lower()
    all_kw = AGENT_KW_STRONG | set(AGENT_KW_WEAK)
    kws = {kw for kw in all_kw if kw in low}
    for hist_kws, dur in reversed(task_history):
        if kws & hist_kws:
            return max(1, round(dur / 60))
    if any(k in low for k in ["翻译", "查", "搜索", "查询", "查找", "查一下"]):
        return 1
    if any(k in low for k in ["发送", "发到", "telegram", "tg", "邮件"]):
        return 3
    if any(k in low for k in ["文件", "excel", "pdf", "表格", "整理"]):
        return 3
    return 2


def _today_output_dir():
    """返回今天的输出目录路径, 自动创建."""
    import datetime as dt
    d = os.path.join(cfg.output_path, dt.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    return d


async def call_openclaw(assistant, task):
    """带进度播报的 agent 调用."""
    ctx = assistant._format_context()
    parts = [_agent_preamble()]
    if ctx:
        parts.append(ctx)
    parts.append(f"当前任务: {task}")
    full_msg = "\n\n".join(parts)
    low = task.lower()
    all_kw = AGENT_KW_STRONG | set(AGENT_KW_WEAK)
    kws = {kw for kw in all_kw if kw in low}

    est = estimate_minutes(task, assistant._task_history)
    announce = f"Bandy正在处理，预计{est}分钟完成"
    print(f"🤖 {announce}", flush=True)
    assistant._announce(announce)

    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "openclaw", "agent", "--agent", "main",
            "--message", full_msg, "--json", "--timeout", "600",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

        comm_task = asyncio.create_task(proc.communicate())
        last_update = start
        while True:
            done, _ = await asyncio.wait({comm_task}, timeout=30)
            if done:
                break
            now = time.time()
            if now - last_update >= 300:
                elapsed_m = int((now - start) / 60)
                remain = max(1, est - elapsed_m)
                msg = f"Bandy还在处理中，已经{elapsed_m}分钟了，预计还需{remain}分钟"
                print(f"🤖 {msg}", flush=True)
                assistant._announce(msg)
                last_update = now
            if now - start > 600:
                try:
                    proc.kill()
                except Exception:
                    pass
                assistant._task_history.append((kws, now - start))
                return "任务超时了，Bandy会在后台继续处理"

        stdout, stderr = comm_task.result()
        duration = time.time() - start
        assistant._task_history.append((kws, duration))
        if len(assistant._task_history) > 50:
            assistant._task_history = assistant._task_history[-50:]

        if proc.returncode == 0 and stdout:
            try:
                d = json.loads(stdout.decode())
                reply = d.get("result", {}).get("payloads", [{}])[0].get("text", "")
            except (KeyError, IndexError, json.JSONDecodeError):
                reply = stdout.decode().strip()
            result = strip_markdown(reply) if reply else "已完成"
            dm = round(duration / 60, 1)
            print(f"✅ 任务完成 ({dm}分钟)", flush=True)

            tg_sent = await auto_send_tg(assistant, reply or "", start)
            dm_str = f"用时{dm}分钟"
            if tg_sent:
                return f"任务完成，{dm_str}，文件已发到你的TG"
            return f"任务完成，{dm_str}。{result}"
        err = stderr.decode().strip() if stderr else ""
        print(f"❌ agent 错误: {err}", flush=True)
        return "执行任务时出错了，请稍后再试"
    except Exception as e:
        print(f"❌ agent 异常: {e}", flush=True)
        return "执行出错了，请再试一次"


async def auto_send_tg(assistant, reply, start_time):
    """自动检测并发送 agent 生成的文件到 TG, 跨任务去重."""
    sent_this_call = set()
    for f in _FILE_RE.findall(reply):
        path = os.path.expanduser(f)
        if os.path.isfile(path) and path not in assistant._tg_sent_files:
            ok = await send_tg_file(path, caption=os.path.basename(path))
            if ok:
                print(f"📤 已发送到 TG: {path}", flush=True)
                assistant._tg_sent_files.add(path)
                sent_this_call.add(path)

    for scan_dir in [cfg.output_path, cfg.PROJECT_ROOT]:
        try:
            for fname in os.listdir(scan_dir):
                if fname.endswith(_OUTPUT_EXTS):
                    fpath = os.path.join(scan_dir, fname)
                    if os.path.getmtime(fpath) >= start_time and fpath not in assistant._tg_sent_files:
                        ok = await send_tg_file(fpath, caption=fname)
                        if ok:
                            print(f"📤 已发送到 TG: {fpath}", flush=True)
                            assistant._tg_sent_files.add(fpath)
                            sent_this_call.add(fpath)
        except Exception:
            pass
    return bool(sent_this_call)


async def run_agent_bg(assistant, task):
    """后台运行 agent, 不阻塞语音交互. 完成后通过队列播报."""
    try:
        print(f"🔧 后台任务: {task}", flush=True)
        result = await call_openclaw(assistant, task)
        if result:
            assistant._record("assistant", result)
            print(f"🤖 回复: {result}", flush=True)
            assistant._announce(result)
    except Exception as e:
        print(f"❌ 后台任务错误: {e}", flush=True)
        assistant._announce("任务执行出错了")
