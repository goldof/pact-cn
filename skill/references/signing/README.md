# Pact 官方签名 · 密钥管理

## 现状

- 算法：minisign（Ed25519），0.12。
- 密钥 ID：`C015BAA2CE0E93FF`，2026-09-30 生成。
- 私钥：只在作者本地机器 `~/.config/pact/minisign.key`（权限 600，空密码——靠文件权限保护，与 SSH 私钥同模型）。**永不进云 VM、不进 git、不进聊天。**
- 公钥：`references/signing/pubkey.txt`（系统层，指纹覆盖）＋ 官方 GitHub 仓库公示（push 后填地址）。两处对不上时，以 GitHub 公示为准。

## 发版签名流程

`scripts/release.sh` 在生成 `FINGERPRINTS.md` 后自动走远程签名：把文件 base64 传到作者本地机器，用私钥签完，把 `.minisig` 传回来。签不出则发版**失败停下**（fail-closed），除非显式 `SKIP_SIGN=1`（此时该版本无官方签名，须在 CHANGELOG 注明）。

## 轮换

1. 本地生成新密钥对（`minisign -G`），旧私钥归档不删（老版本验证还用得到）。
2. 新公钥替换 `references/signing/pubkey.txt`，更新本文件与 SKILL.md 中的密钥 ID。
3. GitHub 公示同步更新，注明轮换日期与原因。
4. 发新版并签名。

## 失窃响应

私钥一旦疑似泄露：立即按"轮换"走一遍；在 GitHub 公示页声明旧公钥作废日期；此后旧公钥签出的新版本一律视为可疑。
