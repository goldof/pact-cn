# Pact 守约 · 中国版（v0.4.0）

交易约定的生命周期保管人，跑在 **WorkBuddy 本地** 的版本。

## 版本边界

- 仅支持 **A 股**（沪深北）。加密货币、美股/港股等境外标的不支持——这是版本定义，不可配置。
- 数据只存本机（`~/.pact-cn/`，Windows 下是 `%USERPROFILE%\.pact-cn`），**不出境**。
- 海外版（美股/加密/A股，跑 Muse 云端）是另一个包，两版数据不互通。

## 包结构

```
pact-cn/
  skill/                  ← 新版 skill（方法论＋交互）
    SKILL.md              ← 中国版 skill（A股 only、数据不出境）
    references/           ← 方法论核心（铁律、状态机、生命周期…）
    data/commitments.example.json
    user/overlay.md       ← 你的定制层（官方更新不覆盖）
  server/                 ← 服务端（本地 loop，本机跑）
    check.py              ← 每日检查：跟踪状态、生成提醒文案（唯一行情耦合点是 fetch_prices）
    prices.py             ← 行情源（腾讯→新浪→网易，免费直连）
    events.py             ← 行为事件日志（写路径，append-only SQLite）
    stats.py              ← 个人统计（读路径的自复用一半：轨迹/base rate/画像）
    render_board.py       ← 看板渲染
    templates/board.html
```

## 数据流

```
记约定（WorkBuddy 对话）
  → commitments.json
  → check.py（定时任务，每天收盘后）：比对现价 vs 证伪线 → 状态机 → 提醒文案
  → events.py append-check：事件进本地库（created/state_changed/reminder_sent）
  → 提醒推送给你 → 你复盘/归档
  → stats.py：随时看"你自己的历史"（轨迹、个人 base rate、心智刻度）
```

铁律：只做记录、提醒、归档。**提醒≠建议**，绝不输出买卖判断。

## 安装

见 `INSTALL.md`。
