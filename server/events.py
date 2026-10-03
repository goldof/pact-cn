#!/usr/bin/env python3
"""Pact 行为事件日志（中国版·单用户本地版，v0.4.0）—— L2 写路径。

设计：
- append-only 事件记录（写路径），库只落本机（$PACT_CN_HOME/pact_events.db），不出境。
- 读路径：自复用（stats.py，个人统计）现在就开；跨用户聚合以后再说。
- 隐私：证伪条件原话永不进库；本机单用户，user_hash 固定为 local。

事件表 commitment_events：
  ts, user_hash, commitment_id, ticker, event_type,
  from_state, to_state, d, specificity, price, response_action, note

  event_type: created | state_changed | reminder_sent | responded
  d: σ 归一化线位距离 = ((现价-证伪价)/现价) / 日波动率σ，
     σ 取 price_history 日对数收益率的样本标准差。跨标的可比口径。
  specificity: 判据具体性启发式打分 0..1（v0 启发式：含数字/含时间词/
     含可观测动词各占 1/3），非科学量表，仅供工程参考。

用法：
  events.py init                          # 建库建表
  events.py seed                          # 回填已有约定的 created 事件（幂等）
  events.py append-check <check.json>     # 从 check.py 输出 JSON 追加事件（幂等）
"""
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

HOME = os.environ.get("PACT_CN_HOME", os.path.expanduser("~/.pact-cn"))
DB_PATH = os.path.join(HOME, "pact_events.db")
COMMITMENTS_PATH = os.environ.get(
    "CHENGNUO_DATA", os.path.join(HOME, "commitments.json"))
USER = "local"  # 本机单用户

SCHEMA = """
CREATE TABLE IF NOT EXISTS commitment_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_hash TEXT NOT NULL,
  commitment_id TEXT NOT NULL,
  ticker TEXT,
  event_type TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT,
  d REAL,
  specificity REAL,
  price REAL,
  response_action TEXT,
  note TEXT,
  UNIQUE(user_hash, commitment_id, event_type, ts)
);
CREATE INDEX IF NOT EXISTS idx_events_user_commit
  ON commitment_events(user_hash, commitment_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_type
  ON commitment_events(event_type, ts);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def sigma_daily(price_history):
    """price_history: [[date, close], ...] → 日对数收益率样本标准差。"""
    closes = [p[1] for p in price_history if p[1] and p[1] > 0]
    if len(closes) < 3:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) if var > 0 else None


def line_distance_d(price, falsify_price, price_history):
    """d = ((现价-证伪价)/现价) / 日波动率σ。None 表示算不出。"""
    try:
        if not price or not falsify_price or price <= 0:
            return None
        sig = sigma_daily(price_history or [])
        if not sig:
            return None
        return ((price - falsify_price) / price) / sig
    except (TypeError, ValueError):
        return None


def specificity_score(condition):
    """判据具体性启发式打分 0..1（v0，非科学量表）。"""
    if not condition:
        return None
    s = 0.0
    if re.search(r"\d", condition):
        s += 1 / 3
    if re.search(r"日|周|月|天|收盘|开盘|交易日", condition):
        s += 1 / 3
    if re.search(r"跌破|突破|高于|低于|达到|连续", condition):
        s += 1 / 3
    return round(s, 3)


def insert_event(conn, **kw):
    cols = ["ts", "user_hash", "commitment_id", "ticker", "event_type",
            "from_state", "to_state", "d", "specificity", "price",
            "response_action", "note"]
    vals = [kw.get(c) for c in cols]
    try:
        conn.execute(
            f"INSERT INTO commitment_events ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})", vals)
        return True
    except sqlite3.IntegrityError:
        return False  # 幂等：重复事件跳过


def load_commitments():
    with open(COMMITMENTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["commitments"] if isinstance(data, dict) else data


def cmd_seed():
    conn = get_db()
    commitments = load_commitments()
    added = 0
    for c in commitments:
        d = line_distance_d(c.get("current_price"), c.get("falsify_price"),
                            c.get("price_history"))
        spec = specificity_score(c.get("falsify_condition"))
        ok = insert_event(
            conn, ts=c.get("created_at") or now_iso(), user_hash=USER,
            commitment_id=c.get("id"), ticker=c.get("ticker"),
            event_type="created", to_state=c.get("state"), d=d,
            specificity=spec, price=c.get("current_price"),
            note="seed: 回填已有约定的创建事件")
        added += ok
    conn.commit()
    print(json.dumps({"seeded": added, "total": len(commitments),
                      "db": DB_PATH}, ensure_ascii=False))


def cmd_append_check(check_json_path):
    with open(check_json_path, encoding="utf-8") as f:
        summary = json.load(f)
    ts = summary.get("checked_at") or now_iso()
    conn = get_db()
    counts = {"state_changed": 0, "reminder_sent": 0}
    cmap = {c.get("id"): c for c in load_commitments()}
    for t in summary.get("transitions", []):
        c = cmap.get(t.get("commitment_id"))
        if not c:
            continue
        d = line_distance_d(c.get("current_price"), c.get("falsify_price"),
                            c.get("price_history"))
        ok = insert_event(
            conn, ts=ts, user_hash=USER, commitment_id=t.get("commitment_id"),
            ticker=c.get("ticker"), event_type="state_changed",
            from_state=t.get("from"), to_state=t.get("to"), d=d,
            specificity=specificity_score(c.get("falsify_condition")),
            price=c.get("current_price"), note=t.get("reason"))
        counts["state_changed"] += ok
    for r in summary.get("reminders", []):
        c = cmap.get(r.get("commitment_id"))
        if not c:
            continue
        ok = insert_event(
            conn, ts=ts, user_hash=USER, commitment_id=r.get("commitment_id"),
            ticker=r.get("ticker") or c.get("ticker"),
            event_type="reminder_sent",
            from_state=None, to_state=c.get("state"),
            price=c.get("current_price"), note=r.get("trigger"))
        counts["reminder_sent"] += ok
    conn.commit()
    print(json.dumps({"appended": counts, "db": DB_PATH}, ensure_ascii=False))


def main(argv):
    if len(argv) < 2 or argv[1] not in ("init", "seed", "append-check"):
        print(__doc__)
        return 1
    if argv[1] == "init":
        get_db().close()
        print(json.dumps({"ok": True, "db": DB_PATH}, ensure_ascii=False))
    elif argv[1] == "seed":
        cmd_seed()
    else:
        if len(argv) < 3:
            print("用法: events.py append-check <check.json>", file=sys.stderr)
            return 1
        cmd_append_check(argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
