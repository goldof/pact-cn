#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pact_cn.paths —— 跨环境持久化路径解析（参考实现）

解析优先级（第一个"可写且属持久卷"的胜出）：
  1) $PACT_HOME        —— 显式覆盖，任何环境最高优先（运维可强制指定）
  2) /workspace/.pact-cn —— 云端用户持久卷（项目级）。云端 $HOME(/root) 不持久，
                            只有 /workspace 这类用户卷在重置后保留
  3) ~/.pact-cn        —— 本地经典回退（用户机器 ~ 持久）

所有读写台账的入口都应 import 本模块，禁止散落硬编码 "~/.pact-cn"。
"""

import os
import sys

# 云端用户持久卷根（项目级）。如你的云端环境持久卷路径不同，改这里。
CLOUD_VOLUME = "/workspace"
# 数据子目录名
SUBDIR = ".pact-cn"
# 向后兼容软链位置（手动 / 旧 cron 仍可用）
COMPAT_SYMLINK = "~/.pact-cn"


def resolve_data_dir(env=None) -> str:
    """返回 pact 数据的单一可信源目录（绝对路径，已确保存在可写）。"""
    env = env if env is not None else os.environ

    # 1) 显式覆盖（最高优先）
    home = env.get("PACT_HOME")
    if home:
        return _ensure(os.path.expanduser(home))

    # 2) 云端持久卷：/workspace 存在且可写
    if _writable_dir(CLOUD_VOLUME):
        return _ensure(os.path.join(CLOUD_VOLUME, SUBDIR))

    # 3) 本地经典回退
    return _ensure(os.path.expanduser("~/" + SUBDIR))


def _writable_dir(path: str) -> bool:
    return os.path.isdir(path) and os.access(path, os.W_OK)


def _ensure(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def ensure_compat_symlink(data_dir: str) -> None:
    """在 ~/.pact-cn 处建软链指向 data_dir（若缺失/损坏），保持手动与旧路径可用。

    行为：
      - 已是正确软链 → 不动
      - 软链指向错误 → 重建
      - 是旧真实目录 → 不覆盖（迁移另行处理），仅告警
      - 无权限等 → 静默失败，不影响核心（DATA_DIR 已可用）
    """
    link = os.path.expanduser(COMPAT_SYMLINK)
    target = os.path.abspath(data_dir)
    try:
        if os.path.islink(link):
            if os.path.realpath(link) == target:
                return
            os.unlink(link)
        elif os.path.exists(link):
            # 旧真实目录：保留，避免误吞数据；迁移逻辑见 migrate_legacy()
            sys.stderr.write(
                f"[pact] 发现旧真实目录 {link}，未覆盖；如需合并请调用 migrate_legacy()\n"
            )
            return
        # 父目录可能不存在（如隔离/容器 HOME），先确保可建软链
        parent = os.path.dirname(link)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.symlink(target, link)
    except OSError as e:
        sys.stderr.write(f"[pact] 兼容软链创建失败（可忽略）：{e}\n")


def migrate_legacy(force: bool = False) -> bool:
    """把旧真实目录 ~/.pact-cn 的内容并入 DATA_DIR（幂等，重复跑安全）。

    返回是否执行了迁移。正式接入时建议在首次启动时调用一次。
    """
    link = os.path.expanduser(COMPAT_SYMLINK)
    if os.path.islink(link) or not os.path.exists(link):
        return False  # 不是旧真实目录，无需迁移
    data_dir = resolve_data_dir()
    if link == os.path.abspath(data_dir):
        return False
    import shutil

    for name in os.listdir(link):
        src = os.path.join(link, name)
        dst = os.path.join(data_dir, name)
        if os.path.exists(dst):
            if not force:
                continue
        if os.path.isfile(src):
            shutil.copy2(src, dst)
        # 子目录（如历史归档）可扩展递归；此处仅处理顶层文件
    if force:
        # 迁移完成后把旧目录转交兼容软链，避免下次重复迁移
        ensure_compat_symlink(data_dir)
    return True


if __name__ == "__main__":
    d = resolve_data_dir()
    ensure_compat_symlink(d)
    print("PACT_DATA_DIR=" + d)
