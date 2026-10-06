# Pact 守约中国版 · 安装指南（WorkBuddy）

## 0. 环境要求

- Windows（WorkBuddy 无 Linux 版），Python 3.8+
- WorkBuddy 已安装并登录

## 1. 装 skill

把 `skill/` 整个目录装进 WorkBuddy 的 Skills（按 WorkBuddy 的"从本地导入 Skill"流程操作）。
装完对 WorkBuddy 说"记约定"，走一遍提交流程，确认 skill 正常触发。

## 2. 准备数据目录

默认数据目录是 `%USERPROFILE%\.pact-cn`（可用环境变量 `PACT_CN_HOME` 改位置）。

```bat
mkdir %USERPROFILE%\.pact-cn
copy skill\data\commitments.example.json %USERPROFILE%\.pact-cn\commitments.json
```

然后按你的持仓改 `commitments.json`（或直接在 WorkBuddy 里用"记约定"一条条录）。

## 3. 初始化事件库

```bat
cd server
python events.py init
python events.py seed
```

`seed` 会把已有约定的 created 事件回填进库（幂等，可重复跑）。

## 4. 建定时任务（每天收盘后跑一次）

在 WorkBuddy 里建一个定时任务，每天 16:05（A 股收盘后）执行：

```bat
cd /d <解压路径>\server && python check.py > %USERPROFILE%\.pact-cn\last_check.json && python events.py append-check %USERPROFILE%\.pact-cn\last_check.json
```

check.py 输出 JSON 到 stdout：有 `reminders` 时，WorkBuddy 按 skill 协议把提醒文案推送给你。

没有定时任务也能用：对 WorkBuddy 说"看板"，手动触发一次检查。


> 注意：定时任务命令里的路径是本机特定的——文档里的是示例，接收方须按自己的实际路径重建。删 skill 不会自动停任务，卸载前先停任务。

### 4.1 云端沙盒持久化（WorkBuddy 云端定时任务）

云端沙盒的 `$HOME`（`/root`）在环境重置后会被清空，台账不能放在 `~/.pact-cn`。
`server/check.py` 已接入 `server/paths.py`，启动时按以下优先级解析数据目录：

1. `$PACT_CN_HOME`（已有安装沿用，最高优先）
2. `$PACT_HOME`
3. `/workspace/.pact-cn`（云端持久卷，重置后保留）
4. `~/.pact-cn`（本地回退）

云端定时任务请用路径无关启动器（`pact-inspect` 须与 `check.py`、`paths.py` 在同一持久目录，
如 `/workspace/.pact-cn/`），命令示例：

```bash
PACT_HOME=/workspace/.pact-cn /workspace/.pact-cn/pact-inspect > /workspace/.pact-cn/last_check.json
```

启动时会自动在 `~/.pact-cn` 建软链指向实际数据目录（自愈；旧真实目录不会被覆盖）。
首次启动如需把旧 `~/.pact-cn` 数据并入，可手动跑一次 `python3 -c "from paths import migrate_legacy; migrate_legacy(force=True)"`。

## 5. 推送

在 WorkBuddy 里打开定时任务的推送（微信/系统通知），提醒文案才能"递"到你手上。

## 6. 验证（不上真实数据先跑通）

```bat
python check.py --sim-drop c1:6
```

模拟 c1 的取回价再跌 6%，看状态机转不转、提醒文案出不出。确认无误后正常跑。

## 7. 自复用：看你自己的历史

```bat
python stats.py
```

随时看轨迹、个人 base rate、判据具体性均值。复盘时先跑一遍再聊。

## 升级

官方更新时整体替换 `skill/SKILL.md` + `skill/references/` 即可；`skill/user/overlay.md` 和 `%USERPROFILE%\.pact-cn\` 下的数据永远不会被覆盖。
