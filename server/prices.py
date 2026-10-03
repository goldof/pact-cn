#!/usr/bin/env python3
"""自建 A 股价格源：腾讯 -> 新浪 -> 网易，三源 fallback。

只解决 check.py 的唯一需求：{ticker6: (price, qdate)}。
无鉴权、无登录、无费用、无需我方提供任何数据服务——用户在自己机器上跑。
任一源超时/格式异常自动降级下一源。

ticker 格式：6 位数字，如 "300580"（与 commitments.json 一致）。

实测记录（2026-09-29，Omarchy 家用网络）：
- 腾讯 qt.gtimg.cn：直通，无需特殊头；现价 index 3，日期时间 index 30
  （"YYYYMMDDHHMMSS" 取前 8 位）。
- 新浪 hq.sinajs.cn：需 Referer 头（http://finance.sina.com.cn），否则 403；
  现价 index 3，日期 index 30（"YYYY-MM-DD"）。
- 网易 api.money.126.net/data/feed：代码前缀 0=上证/1=深证。
"""
import json
import re
import urllib.request
from datetime import timedelta, timezone

BJ = timezone(timedelta(hours=8))
TIMEOUT = 10


def _mkt(ticker):
    t = ticker.strip()
    return "sh" if t.startswith(("60", "68", "9")) else "sz"


def _get(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("gbk", "ignore")


def _ok(price, qdate):
    """归一化为 (float price, "YYYYMMDD")，不合格返回 None。"""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    digits = re.sub(r"\D", "", qdate or "")
    if p <= 0 or len(digits) < 8:
        return None
    return p, digits[:8]


def _from_tencent(ticker):
    m = _mkt(ticker)
    body = _get(f"http://qt.gtimg.cn/q={m}{ticker}")
    mm = re.search(r'"([^"]*)"', body)
    if not mm:
        return None
    f = mm.group(1).split("~")
    if len(f) < 32:
        return None
    return _ok(f[3], f[30])


def _from_sina(ticker):
    m = _mkt(ticker)
    body = _get(f"http://hq.sinajs.cn/list={m}{ticker}",
                {"Referer": "http://finance.sina.com.cn"})
    mm = re.search(r'"([^"]*)"', body)
    if not mm:
        return None
    f = mm.group(1).split(",")
    if len(f) < 32:
        return None
    return _ok(f[3], f[30])


def _from_netease(ticker):
    m = _mkt(ticker)
    code = ("0" if m == "sh" else "1") + ticker
    raw = _get(f"https://api.money.126.net/data/feed/{code}")
    d = json.loads(raw).get(code)
    if not d:
        return None
    return _ok(d.get("price"), (d.get("time") or "")[:10])


_SOURCES = (_from_tencent, _from_sina, _from_netease)


def get_price(ticker):
    """返回 (price, qdate)；三源全失败返回 None。"""
    for src in _SOURCES:
        try:
            r = src(ticker)
            if r:
                return r
        except Exception:
            continue
    return None


def fetch_all(tickers):
    """返回 {ticker: {"price":..., "qdate":"YYYYMMDD"}}；取不到的不在结果里。"""
    out = {}
    for t in tickers:
        r = get_price(t)
        if r:
            out[t] = {"price": r[0], "qdate": r[1]}
    return out


if __name__ == "__main__":
    import sys
    for t in sys.argv[1:]:
        print(t, get_price(t))
