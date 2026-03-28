"""天气查询: wttr.in + macOS Weather 组件定位"""
import os
import re
import datetime as dt

from .config import cfg

_WEATHER_STRIP = re.compile(
    r'(?:怎么样|怎样|如何|多少度|几度|好不好|冷不冷|热不热|'
    r'查一下|查查|查询|看看|播报|说说|告诉我|帮我查|'
    r'天气|气温|温度|预报|'
    r'[的呢吗啊呀吧哦噢啦嘛嗯哎？?!！，。,.])')

_CITY_RE = re.compile(r'([\u4e00-\u9fff]{2,6}?)(?:的)?(?:天气|气温|温度|预报)')
_DAY_WORDS = re.compile(
    r'(?:大前天|大后天|前天|后天|昨天|今天|今日|明天|明日|'
    r'上上?(?:周|星期)[一二三四五六日天]|下下?(?:周|星期)[一二三四五六日天]|'
    r'这?(?:周|星期)[一二三四五六日天])')


def _parse_day_offset(text):
    for word, off in [("大前天", -3), ("前天", -2), ("昨天", -1), ("今天", 0), ("今日", 0),
                      ("明天", 1), ("明日", 1), ("大后天", 3), ("后天", 2)]:
        if word in text:
            return off, word
    wd_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    today_wd = dt.date.today().weekday()
    for pfx, wo in [("上上周", -2), ("上上星期", -2), ("上周", -1), ("上星期", -1),
                     ("下下周", 2), ("下下星期", 2), ("下周", 1), ("下星期", 1),
                     ("这周", 0), ("这个星期", 0), ("这星期", 0), ("周", 0), ("星期", 0)]:
        for dn, dnum in wd_map.items():
            full = pfx + dn
            if full in text:
                return (dnum - today_wd if wo == 0 else wo * 7 + dnum - today_wd), full
    return 0, "今天"


def parse_weather_query(text):
    day_off, day_zh = _parse_day_offset(text)
    m = _CITY_RE.search(text)
    if m:
        raw = m.group(1)
        raw = _DAY_WORDS.sub("", raw)
        raw = _WEATHER_STRIP.sub("", raw).strip()
        if raw and raw[0] == "天" and len(raw) > 2 and day_off == 0 and day_zh == "今天":
            raw = raw[1:]
            day_off = 1
            day_zh = "明天"
        city = raw or None
    else:
        cleaned = text
        if day_zh != "今天" or "今天" in text:
            cleaned = cleaned.replace(day_zh, "", 1)
        cleaned = _WEATHER_STRIP.sub("", cleaned).strip()
        cjk_count = sum(1 for c in cleaned if '\u4e00' <= c <= '\u9fff')
        city = cleaned if cjk_count >= 2 else None
    return city, day_off, city, day_zh


def _get_weather_widget_location():
    import sqlite3
    db = os.path.expanduser(
        "~/Library/Containers/com.apple.weather/Data/Library/Caches/com.apple.weather/Cache.db")
    if not os.path.exists(db):
        return None
    try:
        rows = sqlite3.connect(db).execute(
            "SELECT request_key FROM cfurl_cache_response "
            "WHERE request_key LIKE '%weatherkit.apple.com/api/v2/weather/%' ORDER BY rowid DESC"
        ).fetchall()
        if not rows:
            return None
        seen, batch = set(), []
        for (url,) in rows:
            seg = url.split("/api/v2/weather/")[1].split("/")
            lat, lon = seg[1], seg[2].split("?")[0]
            key = (round(float(lat), 1), round(float(lon), 1))
            if key in seen:
                break
            seen.add(key)
            batch.append(f"{lat},{lon}")
        return batch[-1] if batch else None
    except Exception:
        return None


_cached_location = None


def _get_system_location():
    global _cached_location
    if _cached_location is not None:
        return _cached_location
    if cfg.LOCATION_OVERRIDE:
        _cached_location = cfg.LOCATION_OVERRIDE
    else:
        _cached_location = _get_weather_widget_location() or ""
    if _cached_location:
        print(f"📍 定位: {_cached_location}", flush=True)
    return _cached_location


def get_weather(city=None, day_offset=0, city_display=None, day_zh="今天"):
    import requests
    if day_offset < 0:
        return f"抱歉，暂不支持查询{day_zh}的历史天气"
    if day_offset > 2:
        return f"抱歉，天气预报最多只能查到后天，{day_zh}的还查不了"

    base_loc = city or _get_system_location() or ""
    candidates = [base_loc]
    if city and len(city) > 2:
        candidates.append(city[1:])

    proxy = {"http": cfg.PROXY_HTTP, "https": cfg.PROXY_HTTPS}

    def _desc(obj):
        try:
            return obj['lang_zh'][0]['value']
        except Exception:
            pass
        try:
            return obj['weatherDesc'][0]['value']
        except Exception:
            return ""

    def _format(data, name):
        if day_offset == 0:
            c = data['current_condition'][0]
            return (f"{name}今天天气{_desc(c)}，当前温度{c['temp_C']}度，"
                    f"湿度{c['humidity']}%，风速每小时{c['windspeedKmph']}公里")
        f = data['weather'][day_offset]
        return (f"{name}{day_zh}天气{_desc(f['hourly'][4])}，"
                f"最高{f['maxtempC']}度，最低{f['mintempC']}度")

    last_err = None
    for loc in candidates:
        url = f"https://wttr.in/{loc}?format=j1&lang=zh"
        for px in [proxy, None]:
            try:
                resp = requests.get(url, timeout=10, proxies=px)
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    continue
                data = resp.json()
                if 'current_condition' not in data:
                    last_err = "city_not_found"
                    continue
                name = city_display or (loc if loc != base_loc else None) or "当前位置"
                return _format(data, name)
            except Exception as e:
                import requests as _req
                if isinstance(e, _req.exceptions.ConnectionError):
                    last_err = "network"
                else:
                    last_err = str(e)
                continue

    if last_err == "network":
        return "查询天气失败，网络连接异常"
    if city:
        return f"没有找到{city_display or city}的天气信息，请确认城市名称"
    return "查询天气失败，请检查网络连接"
