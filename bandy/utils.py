"""文本工具: 繁简转换、语言检测、Markdown 清理"""
import re

from opencc import OpenCC as _OpenCC

_cc = _OpenCC('t2s')


def to_simplified(t):
    return _cc.convert(t)


def detect_lang(text):
    zh = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    return 'zh' if zh >= en else 'en'


_TOOL_CALL_RE = re.compile(
    r'<\w*:?tool_call>[\s\S]*?</\w*:?tool_call>'
    r'|<\w*:?tool_call>[\s\S]*'
    r'|<invoke\b[\s\S]*?</invoke>'
    r'|<\|plugin\|>[\s\S]*?<\|/plugin\|>'
    r'|```tool_code[\s\S]*?```',
    re.IGNORECASE)


def strip_tool_calls(text):
    """移除 LLM 返回中的 tool call / function call XML"""
    return _TOOL_CALL_RE.sub('', text).strip()


def strip_markdown(text):
    text = strip_tool_calls(text)
    for pat, rep in [
        (r'```[\s\S]*?```', ''), (r'`([^`]*)`', r'\1'),
        (r'\*\*(.+?)\*\*', r'\1'), (r'\*(.+?)\*', r'\1'),
        (r'__(.+?)__', r'\1'), (r'_(.+?)_', r'\1'),
        (r'~~(.+?)~~', r'\1'), (r'^#{1,6}\s+', ''),
        (r'\[([^\]]+)\]\([^)]+\)', r'\1'),
        (r'^[\s]*[-*+]\s+', ''), (r'^[\s]*\d+\.\s+', ''),
        (r'^>\s+', ''), (r'---+|===+|\*\*\*+', ''),
        (r'^\|[-:| ]+\|$', ''),
        (r'\|', '，'),
    ]:
        flags = re.M if pat.startswith('^') else 0
        text = re.sub(pat, rep, text, flags=flags)
    text = re.sub(r'，{2,}', '，', text)
    text = re.sub(r'(?:^，|，$)', '', text, flags=re.M)
    return re.sub(r'\n{3,}', '\n\n', text).strip()
