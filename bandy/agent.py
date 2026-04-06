"""OpenClaw Agent 调用与复杂任务检测"""
import os
import re
import json
import time
import asyncio

from .config import cfg
from .utils import strip_markdown
from .telegram import send_tg_file
from .metrics import store, AgentMetric

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
    out_dir = _today_output_dir()
    return (
        f"用户 Telegram chat_id: {cfg.TG_CHAT_ID}。\n"
        f"所有生成的文件必须保存到: {out_dir}\n"
        "重要: 不要自行发送文件到Telegram，只需将文件保存到本地即可，系统会自动发送。\n"
        "如果任务需要发送文本消息到Telegram，可以直接使用该ID。"
    )

_FILE_RE = re.compile(
    r'(?:~/|/Users/)[\w./\-]+\.(?:csv|xlsx?|pdf|txt|json|png|jpg|doc|docx|zip|md)')
_OUTPUT_EXTS = (
    '.csv', '.xlsx', '.xls', '.pdf', '.txt', '.json',
    '.png', '.jpg', '.doc', '.docx', '.zip', '.md')


def needs_agent(text):
    low = text.lower()
    if any(kw in low for kw in AGENT_KW_STRONG):
        return True
    return sum(1 for kw in AGENT_KW_WEAK if kw in low) >= 2


_TASK_CATEGORIES = {
    "search":  (["查", "搜索", "搜一下", "查询", "查找", "查一下", "查一查"], 15),
    "send":    (["发送", "发到", "发给", "转发", "telegram", "tg", "邮件"], 20),
    "file":    (["文件", "文档", "excel", "pdf", "csv", "表格"], 40),
    "create":  (["创建", "生成", "制作", "写一个", "写个"], 30),
    "analyze": (["整理", "汇总", "分析", "总结", "对比", "比较"], 45),
    "translate": (["翻译"], 20),
    "collect": (["收集", "下载", "最新", "新闻", "价格", "股票", "行情"], 25),
}


def _task_kws(text):
    low = text.lower()
    all_kw = AGENT_KW_STRONG | set(AGENT_KW_WEAK)
    return {kw for kw in all_kw if kw in low}


def _task_category(text):
    low = text.lower()
    for cat, (kws, _) in _TASK_CATEGORIES.items():
        if any(k in low for k in kws):
            return cat
    return "general"


def estimate_seconds(task, task_history):
    """基于历史加权匹配 + 分类回退，返回预估秒数."""
    kws = _task_kws(task)
    cat = _task_category(task)

    # 1) weighted match against history (recent entries weigh more)
    candidates = []
    for i, (h_text, h_kws, h_cat, h_dur) in enumerate(task_history):
        if not kws or not h_kws:
            continue
        overlap = len(kws & h_kws)
        union = len(kws | h_kws)
        sim = overlap / union
        if h_cat == cat:
            sim += 0.3
        recency = 0.7 + 0.3 * (i / max(len(task_history), 1))
        score = sim * recency
        if score > 0.2:
            candidates.append((score, h_dur))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        total_w, total_d = 0.0, 0.0
        for w, d in candidates[:5]:
            total_w += w
            total_d += w * d
        return max(5, round(total_d / total_w))

    # 2) average of same category in history
    cat_durs = [h_dur for (_, _, h_cat, h_dur) in task_history if h_cat == cat]
    if cat_durs:
        return max(5, round(sum(cat_durs) / len(cat_durs)))

    # 3) category default
    for c, (_, default_s) in _TASK_CATEGORIES.items():
        if c == cat:
            return default_s

    return 20


def format_eta(seconds):
    """将秒数格式化为可读字符串."""
    if seconds < 60:
        return f"{seconds}秒"
    m = seconds / 60
    if m < 1.5:
        return "1分钟"
    return f"{m:.1f}分钟"


def _today_output_dir():
    """返回今天的输出目录路径, 自动创建."""
    import datetime as dt
    d = os.path.join(cfg.output_path, dt.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    return d


async def call_openclaw(assistant, task):
    """带进度播报的 agent 调用."""
    parts = [_agent_preamble()]

    history = assistant._recent_history(limit=10)
    if history:
        ctx_lines = []
        for h in history:
            role = "用户" if h["role"] == "user" else "助手"
            ctx_lines.append(f"{role}: {h['text']}")
        parts.append("近期对话上下文（供理解用户意图参考）:\n" + "\n".join(ctx_lines))

    parts.append(f"当前任务: {task}")
    full_msg = "\n\n".join(parts)
    kws = _task_kws(task)
    cat = _task_category(task)

    est_s = estimate_seconds(task, assistant._task_history)
    eta_str = format_eta(est_s)
    announce = f"Bandy正在处理，预计{eta_str}完成"
    print(f"🤖 {announce}", flush=True)
    assistant._announce(announce)

    start = time.time()
    update_count = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            "openclaw", "agent", "--agent", "main",
            "--message", full_msg, "--json", "--timeout", "600",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        assistant._child_procs.add(proc)

        comm_task = asyncio.create_task(proc.communicate())
        next_update = max(est_s * 1.5, 45)
        try:
            while True:
                done, _ = await asyncio.wait({comm_task}, timeout=15)
                if done:
                    break
                if not assistant.running:
                    proc.kill()
                    return None
                elapsed = time.time() - start
                if elapsed >= next_update:
                    update_count += 1
                    msg = f"Bandy还在处理中，已经{format_eta(int(elapsed))}了，快好了"
                    print(f"🤖 {msg}", flush=True)
                    assistant._announce(msg)
                    next_update = elapsed + 60
                if elapsed > 600:
                    proc.kill()
                    assistant._task_history.append((task, kws, cat, elapsed))
                    return "任务超时了，Bandy会在后台继续处理"
        finally:
            assistant._child_procs.discard(proc)

        stdout, stderr = comm_task.result()
        duration = time.time() - start
        assistant._task_history.append((task, kws, cat, duration))
        if len(assistant._task_history) > 100:
            assistant._task_history = assistant._task_history[-100:]

        if proc.returncode == 0 and stdout:
            try:
                d = json.loads(stdout.decode())
                reply = d.get("result", {}).get("payloads", [{}])[0].get("text", "")
            except (KeyError, IndexError, json.JSONDecodeError):
                reply = stdout.decode().strip()
            result = strip_markdown(reply) if reply else "已完成"
            dm = round(duration / 60, 1)
            print(f"✅ 任务完成 ({dm}分钟)", flush=True)
            store.record_agent(AgentMetric(
                task=task, result=result[:200], duration=duration,
                category=cat, success=True))

            tg_sent = await auto_send_tg(assistant, reply or "", start)
            dm_str = f"用时{dm}分钟"
            if tg_sent:
                return f"任务完成，{dm_str}，文件已发到你的TG"
            return f"任务完成，{dm_str}。{result}"
        err = stderr.decode().strip() if stderr else ""
        print(f"❌ agent 错误: {err}", flush=True)
        store.record_agent(AgentMetric(
            task=task, result=err[:200], duration=time.time() - start,
            category=cat, success=False))
        return "执行任务时出错了，请稍后再试"
    except Exception as e:
        print(f"❌ agent 异常: {e}", flush=True)
        store.record_agent(AgentMetric(
            task=task, result=str(e)[:200], duration=time.time() - start,
            category=cat, success=False))
        return "执行出错了，请再试一次"


def _collect_new_files_to_output(start_time):
    """将 OpenClaw workspace 根目录新生成的文件移到 output/日期/ 目录."""
    out_dir = _today_output_dir()
    moved = []
    try:
        for fname in os.listdir(cfg.OPENCLAW_WORKSPACE):
            if not fname.endswith(_OUTPUT_EXTS):
                continue
            fpath = os.path.join(cfg.OPENCLAW_WORKSPACE, fname)
            if not os.path.isfile(fpath):
                continue
            if os.path.getmtime(fpath) < start_time:
                continue
            dest = os.path.join(out_dir, fname)
            if os.path.exists(dest):
                base, ext = os.path.splitext(fname)
                dest = os.path.join(out_dir, f"{base}_{int(time.time())}{ext}")
            try:
                os.rename(fpath, dest)
                moved.append(dest)
                print(f"📁 已移动到输出目录: {fname}", flush=True)
            except OSError:
                import shutil
                shutil.move(fpath, dest)
                moved.append(dest)
                print(f"📁 已移动到输出目录: {fname}", flush=True)
    except Exception as e:
        print(f"⚠️ 文件整理失败: {e}", flush=True)
    return moved


async def auto_send_tg(assistant, reply, start_time):
    """自动检测并发送 agent 生成的文件到 TG, 跨任务去重."""
    moved_files = _collect_new_files_to_output(start_time)

    sent_this_call = set()

    async def _send(fpath):
        if fpath in assistant._tg_sent_files or fpath in sent_this_call:
            return
        if not os.path.isfile(fpath):
            return
        ok = await send_tg_file(fpath, caption=os.path.basename(fpath))
        if ok:
            print(f"📤 已发送到 TG: {fpath}", flush=True)
            assistant._tg_sent_files.add(fpath)
            sent_this_call.add(fpath)

    for f in _FILE_RE.findall(reply):
        await _send(os.path.expanduser(f))

    for d in {_today_output_dir(), cfg.output_path}:
        try:
            for fname in os.listdir(d):
                if not fname.endswith(_OUTPUT_EXTS):
                    continue
                fpath = os.path.join(d, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) >= start_time:
                    await _send(fpath)
        except Exception:
            pass

    for fpath in moved_files:
        await _send(fpath)

    return bool(sent_this_call)


async def run_agent_bg(assistant, task):
    """后台运行 agent, 不阻塞语音交互. 完成后通过队列播报."""
    try:
        print(f"🔧 后台任务: {task}", flush=True)
        result = await call_openclaw(assistant, task)
        if result:
            print(f"🤖 回复: {result}", flush=True)
            assistant._announce(result)
    except asyncio.CancelledError:
        print("🔧 后台任务已取消", flush=True)
    except Exception as e:
        print(f"❌ 后台任务错误: {e}", flush=True)
        if assistant.running:
            assistant._announce("任务执行出错了")
