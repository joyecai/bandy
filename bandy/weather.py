"""天气查询: macOS WeatherKit (系统天气) + 城市坐标解析"""
import os
import re
import json
import subprocess
import datetime as dt

from .config import cfg

_SCRIPT = os.path.join(os.path.dirname(__file__), "weatherkit_query.swift")

_WEATHER_STRIP = re.compile(
    r'(?:怎么样|怎样|如何|多少度|几度|好不好|冷不冷|热不热|'
    r'查一下|查查|查询|看看|播报|说说|告诉我|帮我查|'
    r'天气|气温|温度|预报|'
    r'[的呢吗啊呀吧哦噢啦嘛嗯哎？?!！，。,.])')

_CITY_RE = re.compile(r'([\u4e00-\u9fff]{2,6}?)(?:的)?(?:天气|气温|温度|预报)')
_NOT_CITY = {"现在", "目前", "当前", "最近", "今天", "明天", "后天", "昨天", "这里", "那里",
             "外面", "室外", "本地", "附近", "我们", "你们", "他们", "大家", "什么", "怎么"}
_DAY_WORDS = re.compile(
    r'(?:大前天|大后天|前天|后天|昨天|今天|今日|明天|明日|'
    r'上上?(?:周|星期)[一二三四五六日天]|下下?(?:周|星期)[一二三四五六日天]|'
    r'这?(?:周|星期)[一二三四五六日天])')

_CONDITION_ZH = {
    "blowingDust": "扬尘", "clear": "晴", "cloudy": "阴",
    "foggy": "雾", "haze": "霾", "mostlyClear": "晴间多云",
    "mostlyCloudy": "多云间阴", "partlyCloudy": "多云",
    "smoky": "烟雾", "breezy": "微风", "windy": "大风",
    "drizzle": "毛毛雨", "heavyRain": "大雨", "isolatedThunderstorms": "局部雷暴",
    "rain": "雨", "sunShowers": "太阳雨", "scatteredThunderstorms": "雷阵雨",
    "strongStorms": "强雷暴", "thunderstorms": "雷暴",
    "frigid": "严寒", "hail": "冰雹", "hot": "酷热",
    "flurries": "小雪", "sleet": "雨夹雪", "snow": "雪",
    "sunFlurries": "晴间阵雪", "wintryMix": "雨雪混合",
    "blizzard": "暴风雪", "blowingSnow": "吹雪", "freezingDrizzle": "冻毛毛雨",
    "freezingRain": "冻雨", "heavySnow": "大雪", "hurricane": "飓风",
    "tropicalStorm": "热带风暴",
    "Blowing Dust": "扬尘", "Clear": "晴", "Cloudy": "阴",
    "Foggy": "雾", "Haze": "霾", "Mostly Clear": "晴间多云",
    "Mostly Cloudy": "多云间阴", "Partly Cloudy": "多云",
    "Smoky": "烟雾", "Breezy": "微风", "Windy": "大风",
    "Drizzle": "毛毛雨", "Heavy Rain": "大雨",
    "Isolated Thunderstorms": "局部雷暴", "Rain": "雨",
    "Sun Showers": "太阳雨", "Scattered Thunderstorms": "雷阵雨",
    "Strong Storms": "强雷暴", "Thunderstorms": "雷暴",
    "Frigid": "严寒", "Hail": "冰雹", "Hot": "酷热",
    "Flurries": "小雪", "Sleet": "雨夹雪", "Snow": "雪",
    "Sun Flurries": "晴间阵雪", "Wintry Mix": "雨雪混合",
    "Blizzard": "暴风雪", "Blowing Snow": "吹雪",
    "Freezing Drizzle": "冻毛毛雨", "Freezing Rain": "冻雨",
    "Heavy Snow": "大雪", "Hurricane": "飓风",
    "Tropical Storm": "热带风暴",
}

_CITY_COORDS = {
    "北京": (39.90, 116.40), "上海": (31.23, 121.47),
    "广州": (23.13, 113.26), "深圳": (22.54, 114.06),
    "杭州": (30.27, 120.15), "南京": (32.06, 118.80),
    "武汉": (30.58, 114.30), "成都": (30.57, 104.07),
    "重庆": (29.56, 106.55), "西安": (34.26, 108.94),
    "苏州": (31.30, 120.62), "天津": (39.13, 117.20),
    "长沙": (28.23, 112.94), "郑州": (34.75, 113.65),
    "东莞": (23.02, 113.75), "佛山": (23.02, 113.12),
    "济南": (36.67, 117.00), "合肥": (31.86, 117.28),
    "福州": (26.08, 119.30), "厦门": (24.48, 118.09),
    "昆明": (25.04, 102.71), "大连": (38.91, 121.60),
    "沈阳": (41.80, 123.43), "哈尔滨": (45.75, 126.65),
    "长春": (43.88, 125.32), "南昌": (28.68, 115.86),
    "石家庄": (38.04, 114.50), "太原": (37.87, 112.55),
    "贵阳": (26.65, 106.63), "南宁": (22.82, 108.32),
    "兰州": (36.06, 103.83), "海口": (20.04, 110.35),
    "银川": (38.49, 106.23), "西宁": (36.62, 101.78),
    "呼和浩特": (40.84, 111.75), "拉萨": (29.65, 91.13),
    "乌鲁木齐": (43.83, 87.62), "青岛": (36.07, 120.38),
    "无锡": (31.57, 120.30), "常州": (31.81, 119.97),
    "温州": (28.00, 120.67), "宁波": (29.87, 121.54),
    "珠海": (22.27, 113.58), "中山": (22.52, 113.39),
    "惠州": (23.11, 114.42), "汕头": (23.35, 116.68),
    "镇江": (32.19, 119.45), "南通": (32.01, 120.86),
    "扬州": (32.39, 119.42), "徐州": (34.28, 117.19),
    "盐城": (33.38, 120.16), "泰州": (32.46, 119.93),
    "淮安": (33.61, 119.01), "连云港": (34.60, 119.22),
    "宿迁": (33.96, 118.28), "香港": (22.32, 114.17),
    "澳门": (22.20, 113.55), "台北": (25.04, 121.57),
}


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
        if raw in _NOT_CITY:
            raw = ""
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


def _condition_zh(cond: str) -> str:
    return _CONDITION_ZH.get(cond, _CONDITION_ZH.get(cond.replace(" ", ""), cond))


def _query_weatherkit(lat: float, lon: float, day_offset: int) -> dict | None:
    """调用 macOS WeatherKit 查询天气，返回 JSON dict 或 None"""
    try:
        result = subprocess.run(
            ["swift", _SCRIPT, str(lat), str(lon), str(day_offset)],
            capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout.strip())
        if "error" in data:
            return None
        return data
    except Exception:
        return None


def _city_to_coords(city: str) -> tuple[float, float] | None:
    if city in _CITY_COORDS:
        return _CITY_COORDS[city]
    for name, coords in _CITY_COORDS.items():
        if city in name or name in city:
            return coords
    return None


def get_weather(city=None, day_offset=0, city_display=None, day_zh="今天"):
    if day_offset < 0:
        return f"抱歉，暂不支持查询{day_zh}的历史天气"
    if day_offset > 9:
        return f"抱歉，天气预报最多查10天，{day_zh}的还查不了"

    if city:
        coords = _city_to_coords(city)
        if not coords:
            return f"没有找到{city_display or city}的位置信息，请确认城市名称"
        lat, lon = coords
    else:
        loc = _get_system_location()
        if not loc:
            return "无法获取当前位置，请在Mac天气应用中添加一个城市"
        lat, lon = (float(x) for x in loc.split(","))

    data = _query_weatherkit(lat, lon, day_offset)
    if not data:
        return "查询天气失败，请确保Mac天气应用可正常使用"

    name = city_display or city or "当前位置"
    cond = _condition_zh(data.get("condition", ""))

    if data.get("type") == "current":
        temp = data.get("temp", "")
        hum = data.get("humidity", "")
        wind = data.get("wind_kph", "")
        return f"{name}今天天气{cond}，当前温度{temp}度，湿度{hum}%，风速每小时{wind}公里"
    else:
        high = data.get("high", "")
        low = data.get("low", "")
        precip = data.get("precip_chance", 0)
        parts = [f"{name}{day_zh}天气{cond}，最高{high}度，最低{low}度"]
        if precip > 0:
            parts.append(f"降水概率{precip}%")
        return "，".join(parts)
