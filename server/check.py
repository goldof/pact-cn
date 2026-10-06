#!/usr/bin/env python3
"""承诺追踪检查脚本（中国版·单用户本地版，v0.4.0）

按 skill `chengnuo-tracker` 的协议执行五步 loop 中的 跟踪/提醒 部分：
  记录(人工/skill) → 跟踪(本脚本+cron) → 提醒(本脚本生成文案) → 复盘(人工) → 归档(人工)

铁律：只做记录、提醒、归档。绝不输出买卖判断。提醒≠建议。
公开行情只读。所有提醒文案引用用户原话（证伪条件+证伪价）。

数据目录：PACT_CN_HOME（跨环境持久化解析，见 paths.py；可用 CHENGNUO_DATA 环境变量直接覆盖台账路径）
行情源：自建免费价格源（scripts/prices.py：腾讯 -> 新浪 -> 网易 fallback），
  无鉴权、无登录、无费用、无需我方提供任何数据服务——用户在自己机器上跑。
  fetch_prices 是唯一与行情源耦合的函数，换数据源只改它。

用法：
  python3 check.py                      # 真实行情检查
  python3 check.py --sim-drop c2:6      # 模拟：c2 的取回价再跌 6%（测试用）

stdout 输出 JSON summary（transitions / reminders / errors），供定时任务解析；
有 reminders 时，由宿主 agent 按 skill 协议把提醒文案送达用户。
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

BJ = timezone(timedelta(hours=8))
# 中国版数据主目录：跨环境持久化解析（server/paths.py）。
# 优先级：$PACT_CN_HOME（已有安装沿用，最高优先）> $PACT_HOME > /workspace/.pact-cn（云端持久卷，重置保留）
#        > ~/.pact-cn（本地回退）。云端沙盒 $HOME 不持久，禁止硬编码 ~/.pact-cn。
# 所有数据（commitments.json、pact_events.db）只落本机/云端用户卷，不出境。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from paths import resolve_data_dir, ensure_compat_symlink  # noqa: E402
PACT_CN_HOME = os.environ.get("PACT_CN_HOME") or resolve_data_dir()
ensure_compat_symlink(PACT_CN_HOME)  # ~/.pact-cn 软链自愈；失败仅 stderr 告警，不影响主流程
DATA_PATH = os.environ.get("CHENGNUO_DATA",
                           os.path.join(PACT_CN_HOME, "commitments.json"))
WARN_PCT = 0.03  # 距证伪线 ≤3% 进入"接近证伪线"（skill 协议）
REMINDER_COPY = "⏰ 证伪线触发。你当时说的，还算数吗？"
REVIEW_DUE_COPY = "📅 复盘日期到了。你当时说的，还算数吗？"


def now_iso():
    return datetime.now(BJ).isoformat(timespec="seconds")


def fetch_prices(tickers):
    """返回 {ticker: {"price":..., "qdate":"YYYYMMDD"}}；取不到的不在结果里。
    qdate 取自行情时间戳的交易日，用于破位确认规则的交易日计数。
    自建免费源（prices.py：腾讯->新浪->网易 fallback），无鉴权无费用。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from prices import fetch_all
    return fetch_all([t for t in tickers if t])


def parse_sim_drops(argv):
    drops = {}
    i = 0
    while i < len(argv):
        if argv[i] == "--sim-drop" and i + 1 < len(argv):
            cid, pct = argv[i + 1].split(":")
            drops[cid] = float(pct)
            i += 2
        else:
            i += 1
    return drops


def already_reminded(commitment, key=""):
    return any("提醒已送达" in ev.get("text", "") and key in ev.get("text", "")
               for ev in commitment.get("timeline", []))


def add_event(commitment, text):
    commitment.setdefault("timeline", []).append({"t": now_iso(), "text": text})


def check_one(c, prices, sim_drops, today, summary):
    cid = c["id"]
    ticker = c["ticker"]
    quote = prices.get(ticker)
    if not quote:
        summary["errors"].append({"commitment_id": cid,
                                  "error": f"ticker {ticker} 行情缺失，本轮跳过"})
        return
    cur = quote["price"]
    qdate = quote["qdate"]
    sim_tag = ""
    if cid in sim_drops:
        cur = round(cur * (1 - sim_drops[cid] / 100), 2)
        sim_tag = "（模拟）"
    c["current_price"] = cur

    falsify = c["falsify_price"]
    state = c["state"]
    dist = (cur - falsify) / falsify if falsify else 0.0

    # 1) 接近证伪线：持有中 且 0 < dist ≤ 3%
    if state == "持有中" and 0 < dist <= WARN_PCT:
        c["state"] = "接近证伪线"
        reason = f"距证伪线 {dist:+.1%}（现价 {cur}，证伪价 {falsify}）{sim_tag}"
        add_event(c, f"跟踪：{reason}，进入「接近证伪线」，预警一次")
        summary["transitions"].append({
            "commitment_id": cid, "name": c["name"],
            "from": "持有中", "to": "接近证伪线", "reason": reason})
        state = "接近证伪线"

    # 2) 触发：持有中/接近证伪线 且 (现价跌破证伪价 或 复盘日期到期)
    # 破位确认规则（confirm_days，如"3日没收回才算跌破"）：连续 confirm_days 个
    # 交易日收盘跌破才触发；期间收回则观察清零。按行情时间戳的交易日计数，节假日不计。
    if state in ("持有中", "接近证伪线"):
        triggers = []
        remind_key = ""
        confirm_days = int(c.get("confirm_days") or 0)
        broke = cur < falsify
        if broke and confirm_days > 0:
            streak = c.get("break_streak") or {}
            if streak.get("qdate") == qdate:
                days = streak.get("days", 1)
            else:
                days = streak.get("days", 0) + 1
                c["break_streak"] = {"qdate": qdate, "days": days}
                if days < confirm_days:
                    add_event(c, f"跟踪：现价 {cur} 跌破证伪价 {falsify}，"
                                 f"破位观察第 {days}/{confirm_days} 天"
                                 f"（{confirm_days}日未收回才算真跌破）{sim_tag}")
            if days >= confirm_days:
                triggers.append(f"现价 {cur} 跌破证伪价 {falsify}（{confirm_days}日确认）")
                c.pop("break_streak", None)
                remind_key = f"{confirm_days}日确认"
        elif broke:
            triggers.append(f"现价 {cur} 跌破证伪价 {falsify}")
        elif c.pop("break_streak", None) is not None:
            add_event(c, f"跟踪：现价 {cur} 收回证伪价 {falsify} 上方，破位观察清零{sim_tag}")
        try:
            due = date.fromisoformat(c["review_date"])
            if today >= due:
                triggers.append(f"复盘日期 {c['review_date']} 到期")
        except ValueError:
            pass
        if triggers and not already_reminded(c, remind_key):
            c["state"] = "待复盘"
            trigger_text = "；".join(triggers)
            add_event(c, f"跟踪：{trigger_text}{sim_tag}，进入「待复盘」")
            copy = REMINDER_COPY if broke else REVIEW_DUE_COPY
            key_tag = f"（{remind_key}）" if remind_key else ""
            reminder_text = (f"{copy}{key_tag}\n你写下的是：{c['falsify_condition']}"
                             f"证伪价 {falsify}，现价 {cur}。")
            add_event(c, f"提醒已送达{key_tag}{sim_tag}：{copy}")
            summary["transitions"].append({
                "commitment_id": cid, "name": c["name"],
                "from": state, "to": "待复盘", "reason": f"{trigger_text}{sim_tag}"})
            summary["reminders"].append({
                "commitment_id": cid, "name": c["name"],
                "ticker": ticker, "trigger": trigger_text + sim_tag,
                "reminder_text": reminder_text})


def main(argv):
    sim_drops = parse_sim_drops(argv)
    today = datetime.now(BJ).date()
    summary = {"checked_at": now_iso(), "transitions": [], "reminders": [], "errors": []}
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    # 缺失台账视为​​空台账（自动建空文件），不报错；只有"文件损坏"才走 errors（见行为契约 3）
    if not os.path.isfile(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({"commitments": []}, f, ensure_ascii=False, indent=2)
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    commitments = data.get("commitments", [])
    tickers = sorted({c["ticker"] for c in commitments if c.get("state") != "已归档"})
    try:
        prices = fetch_prices(tickers)
    except RuntimeError as e:
        summary["errors"].append({"error": str(e)})
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1
    for c in commitments:
        if c.get("state") == "已归档":
            continue
        check_one(c, prices, sim_drops, today, summary)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
