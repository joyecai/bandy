"""唤醒词检测与剥离"""
import re
import difflib

_WAKE_EN = ["bandy","bendy","bendi","bandi","pandy","pendi","benny","benty","benni","band","bend"]
_WAKE_ZH = ["班底","半底","班迪","半迪","班地","半地","斑底","斑迪","邦迪"]
_FILLER = {"hey","hi","hello","yo","ok","yeah","yes","嗨","喂","你好","嘿","哈喽","哈罗"}


def is_wake_word(text):
    for a in _WAKE_ZH:
        if a in text:
            return True
    low = text.lower().replace(" ", "").replace(",", "").replace(".", "")
    for a in _WAKE_EN:
        if a in low:
            return True
    for w in re.split(r'[\s,!?，。！？]+', text.lower()):
        c = re.sub(r'[^a-z]', '', w)
        if len(c) >= 3 and difflib.SequenceMatcher(None, c, "bandy").ratio() >= 0.6:
            return True
    return False


def strip_wake_word(text):
    """去掉唤醒词和寒暄词, 返回有实际意义的剩余内容."""
    result = text
    for a in _WAKE_ZH:
        result = result.replace(a, "")
    for a in sorted(_WAKE_EN, key=len, reverse=True):
        result = re.sub(re.escape(a), '', result, flags=re.I)
    result = re.sub(r'[\s,，.。、!！?？:：]+', ' ', result).strip()
    words = [w for w in result.split() if w.lower() not in _FILLER]
    result = " ".join(words)
    if not result or len(result) < 2:
        return ""
    if not any(('\u4e00' <= c <= '\u9fff') or c.isalpha() for c in result):
        return ""
    return result
