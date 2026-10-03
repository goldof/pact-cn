#!/usr/bin/env python3
"""Pact 个人统计（中国版·单用户本地版，v0.4.0）—— L2 读路径的自复用一半。

只读本机库（$PACT_CN_HOME/pact_events.db + commitments.json），只算"你自己的历史"：
  - 复盘证据链：每条约定的事件轨迹（一句话）
  - 个人 base rate：证伪成立 / 修订 / 到期复盘的占比
  - 行为画像：平均建仓 d（σ）、判据具体性均值、被提醒次数
  - 心智刻度：specificity 随时间的趋势（v0 只给均值与条数）

不做跨用户统计，不出境。输出 JSON（--json）或人话摘要（默认）。

用法：
  stats.py              # 人话摘要
  stats.py --json       # JSON，供 agent/看板用
"""
import json
import os
import sqlite3
import sys

HOME = os.environ.get("PACT_CN_HOME", os.path.expanduser("~/.pact-cn"))
DB_PATH = os.path.join(HOME, "pact_events.db")
COMMITMENTS_PATH = os.environ.get(
    "CHENGNUO_DATA", os.path.join(HOME, "commitments.json"))


def load():
    commitments = []
    if os.path.isfile(COMMITMENTS_PATH):
        with open(COMMITMENTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        commitments = data.get("commitments", []) if isinstance(data, dict) else data
    events = []
    if os.path.isfile(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        events = [dict(r) for r in conn.execute(
            "SELECT * FROM commitment_events ORDER BY ts")]
        conn.close()
    return commitments, events


def summarize(commitments, events):
    by_id = {}
    for e in events:
        by_id.setdefault(e["commitment_id"], []).append(e)

    states = {}
    for c in commitments:
        states[c.get("state", "?")] = states.get(c.get("state", "?"), 0) + 1

    created = [e for e in events if e["event_type"] == "created"]
    ds = [e["d"] for e in created if e["d"] is not None]
    specs = [e["specificity"] for e in created
             if e["specificity"] is not None]
    n_reminded = len({e["commitment_id"] for e in events
                      if e["event_type"] == "reminder_sent"})
    n_review = len([e for e in events
                    if e["event_type"] == "state_changed"
                    and e["to_state"] == "待复盘"])

    trajectories = []
    cmap = {c.get("id"): c for c in commitments}
    for cid, evs in sorted(by_id.items()):
        name = (cmap.get(cid) or {}).get("name", cid)
        kinds = {}
        for e in evs:
            kinds[e["event_type"]] = kinds.get(e["event_type"], 0) + 1
        parts = []
        if kinds.get("created"):
            d0 = next((e["d"] for e in evs if e["event_type"] == "created"
                       and e["d"] is not None), None)
            parts.append(f"建仓 d={d0:.2f}σ" if d0 is not None else "已创建")
        if kinds.get("state_changed"):
            parts.append(f"状态变化 {kinds['state_changed']} 次")
        if kinds.get("reminder_sent"):
            parts.append(f"被提醒 {kinds['reminder_sent']} 次")
        trajectories.append({"id": cid, "name": name,
                             "summary": "，".join(parts) or "无事件"})

    return {
        "commitments_total": len(commitments),
        "states": states,
        "events_total": len(events),
        "avg_created_d": round(sum(ds) / len(ds), 2) if ds else None,
        "avg_specificity": round(sum(specs) / len(specs), 3) if specs else None,
        "commitments_reminded": n_reminded,
        "commitments_to_review": n_review,
        "trajectories": trajectories,
    }


def human(s):
    lines = [
        f"约定 {s['commitments_total']} 条（{ '、'.join(f'{k} {v}' for k, v in s['states'].items()) or '无'}），"
        f"事件 {s['events_total']} 笔。",
    ]
    if s["avg_created_d"] is not None:
        lines.append(f"建仓时平均距证伪线 {s['avg_created_d']}σ，判据具体性均值 {s['avg_specificity']}。")
    lines.append(f"累计 {s['commitments_reminded']} 条被提醒过，{s['commitments_to_review']} 条进入待复盘。")
    lines.append("轨迹：")
    for t in s["trajectories"]:
        lines.append(f"  · {t['name']}：{t['summary']}")
    return "\n".join(lines)


def main(argv):
    commitments, events = load()
    s = summarize(commitments, events)
    if "--json" in argv:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(human(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
