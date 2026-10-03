# RELEASE.md — 分发注意事项（pact-cn v0.4.1）

## 许可
本包采用 MIT License（见 `LICENSE`）。接收方拥有使用、修改、再分发的完整授权。

## 分发前检查（已处理）
1. **LICENSE** ✓ 已补进包。
2. **签名链**：`references/signing/` 描述了 minisign 官方签名流程，但本包暂未附
   `FINGERPRINTS.md` / `.minisig`。公钥的 canonical 公示位置（官方 GitHub 仓库）
   建好后，发版时补签名。**在此之前**，skill 上岗声明会如实说"无法验证官方签名"——
   这是诚实，不是缺陷。
3. **个人数据** ✓ 已验：包内只有 `commitments.example.json` 示例数据和空白
   `user/overlay.md` 模板，无真实持仓、无事件库。
4. **定时任务路径**：cron 命令里的路径是机器特定的，接收方须按 `INSTALL.md`
   用本机路径重建任务。删 skill 不会自动停任务——卸载前先停任务。

## 分叉与冒充的边界
- 分叉欢迎：改了核心再分发可以，但须如实声明指纹失效，不再是官方验证版本。
- 冒充不欢迎：不得声称未签名的改版是官方 Pact。
- 官方身份凭证 = minisign 签名（仓库建好后启用）。

## 升级路径
系统层（`SKILL.md` + `references/`）官方更新时整体替换；用户层
（`user/overlay.md`、`~/.pact-cn/` 数据）永远不被覆盖。升级前先停旧版定时任务
（按 `pact-<用途>-v<版本>` 命名识别），再装新版。
