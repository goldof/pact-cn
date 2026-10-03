#!/usr/bin/env python3
"""render_board.py — 承诺追踪看板数据渲染器（单用户本地版）。

读取 CHENGNUO_DATA（默认 ~/.chengnuo/commitments.json），生成看板用的
BOARD_DATA JSON。

用法: python3 render_board.py
stdout: BOARD_DATA JSON（一行）
stderr: BOARD_CHANGED=true|false（幂等：payload 无变化时为 false，看板不应被触碰）

只用 stdlib。只读 commitments.json，不回写任何外部系统。
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BJ = timezone(timedelta(hours=8))
PACT_CN_HOME = os.environ.get("PACT_CN_HOME",
                              os.path.expanduser("~/.pact-cn"))
DATA_PATH = os.environ.get("CHENGNUO_DATA",
                           os.path.join(PACT_CN_HOME, "commitments.json"))
HASH_PATH = os.path.join(os.path.dirname(DATA_PATH), ".board_hash")
STATES = ["持有中", "接近证伪线", "待复盘", "已归档"]


def main():
    if not os.path.isfile(DATA_PATH):
        print(json.dumps({"error": f"数据文件不存在: {DATA_PATH}，先按 "
                                   "data/commitments.example.json 建一条承诺"},
                         ensure_ascii=False))
        return 1
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    commitments = []
    counts = {s: 0 for s in STATES}
    for c in data.get("commitments", []):
        fp = c.get("falsify_price")
        cp = c.get("current_price")
        dist = round((cp - fp) / fp * 100, 1) if fp and cp else None
        st = c.get("state")
        if st in counts:
            counts[st] += 1
        commitments.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "ticker": c.get("ticker"),
            "state": st,
            "falsify_price": fp,
            "current_price": cp,
            "dist_pct": dist,
            "review_date": c.get("review_date"),
            "logic": c.get("logic"),
            "falsify_condition": c.get("falsify_condition"),
            "variables": c.get("variables"),
            "review_note": c.get("review_note"),
            "confirm_days": c.get("confirm_days"),
            "timeline": c.get("timeline", []),
        })

    stable = {
        "display_name": "我的承诺看板",
        "virtual": False,
        "counts": counts,
        "commitments": commitments,
    }
    digest = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    changed = True
    if os.path.isfile(HASH_PATH):
        with open(HASH_PATH, encoding="utf-8") as f:
            changed = f.read().strip() != digest
    if changed:
        with open(HASH_PATH, "w", encoding="utf-8") as f:
            f.write(digest)
    board = dict(stable)
    board["engine_run_at"] = datetime.now(BJ).isoformat(timespec="seconds")
    print(json.dumps(board, ensure_ascii=False))
    print(f"BOARD_CHANGED={'true' if changed else 'false'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
