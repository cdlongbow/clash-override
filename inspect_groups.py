#!/usr/bin/env python3
"""体检脚本：只读检查生成的覆盖脚本，不写任何文件。

用法：
    python inspect_groups.py                      # 体检默认产物 my_merged_override.js
    python inspect_groups.py --artifact 某路径.js
    python inspect_groups.py --nodes 60           # 每个地区造 60 个假节点再看
    python inspect_groups.py --json               # 输出机器可读的 JSON

原理：用假节点在 node 里真跑一遍脚本的 main()，把生成的策略组结构打印成表格，
顺便检查几个会让 Clash 拒载或体验变差的点（空组、重名、残留入口类条目）。
退出码 0 表示没问题，1 表示发现问题，2 表示环境缺 node。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import merge_override as mo

ROOT = Path(__file__).resolve().parent
DEFAULT_ARTIFACT = ROOT / "my_merged_override.js"
JUDGED_TOKENS = tuple(mo.DEFAULT_DROP_NAME_TOKENS)
BUILTIN_ENTRY_NAMES = {
    "直连", "拒绝", "放行", "屏蔽", "拦截",
    "direct", "reject", "reject-drop", "pass", "compatible", "global",
}
TOKEN_SPLIT = re.compile(r"[|\s\-/_.:,]+")

HARNESS = """
import { readFileSync } from 'fs'
const src = readFileSync(process.env.ARTIFACT_PATH, 'utf8')
const perRegion = Number(process.env.NODES_PER_REGION || '40')
const regions = [['HK node '], ['US node '], ['JP node ']]
const proxies = []
for (const [prefix] of regions) {
  for (let i = 1; i <= perRegion; i++) {
    proxies.push({ name: prefix + i + ' | x1.5', type: 'vless' })
  }
}
proxies.push({ name: 'Extra Latency 1', type: 'ss' })
proxies.push({ name: 'Extra Latency 2', type: 'ss' })
proxies.push({ name: 'DIRECT entrance', type: 'direct' })
const config = {
  proxies,
  rules: [],
  'proxy-groups': [],
  'proxy-providers': {},
}
const main = new Function('args', 'return (function(){' + src + '\\nreturn main})()')({})
const out = main(config)
const groups = (out['proxy-groups'] || []).map((g) => ({
  name: g.name,
  type: g.type || '',
  proxies: Array.isArray(g.proxies) ? g.proxies : [],
}))
console.log(JSON.stringify({ groups, rules: out.rules || [] }))
"""


def leading_token(name: str) -> str:
    parts = [part for part in TOKEN_SPLIT.split(name.strip().lower()) if part]
    return parts[0] if parts else ""


def display_width(text: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def run_artifact(artifact: Path, nodes_per_region: int) -> dict:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("找不到 node 命令，没法真跑脚本；装好 node 再体检")
    proc = subprocess.run(
        [node, "-e", HARNESS],
        capture_output=True,
        text=True,
        env={
            "ARTIFACT_PATH": str(artifact),
            "NODES_PER_REGION": str(nodes_per_region),
            "PATH": "/usr/local/bin:/usr/bin:/bin",
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"用 node 跑脚本失败：\n{proc.stderr.strip()}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def inspect(summary: dict, auto_max: int) -> list[str]:
    problems: list[str] = []
    groups = summary["groups"]
    names = [group["name"] for group in groups]

    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        problems.append("策略组重名，Clash 会整体拒载: " + "、".join(duplicated))

    for group in groups:
        if not group["proxies"]:
            problems.append(f"策略组 {group['name']} 成员为空，Clash 会拒载")

    for group in groups:
        leftovers = [
            name
            for name in group["proxies"]
            if name.strip().lower() not in BUILTIN_ENTRY_NAMES
            and leading_token(name) in JUDGED_TOKENS
        ]
        if leftovers:
            problems.append(
                f"策略组 {group['name']} 仍混进入口类条目: " + "、".join(leftovers[:3])
            )

    for group in groups:
        if group["type"] == "url-test" and len(group["proxies"]) > auto_max:
            problems.append(
                f"测速组 {group['name']} 有 {len(group['proxies'])} 个成员，超过上限 {auto_max}"
            )
    return problems


def print_table(summary: dict, auto_max: int) -> None:
    groups = summary["groups"]
    print(f"策略组共 {len(groups)} 个，规则共 {len(summary['rules'])} 条")
    print(f"自动选择上限 {auto_max}（超过会提示）\n")
    name_width = max(display_width(group["name"]) for group in groups) + 2
    header = pad("策略组", name_width) + "  类型        成员  备注"
    print(header)
    print("-" * (name_width + 28))
    for group in sorted(groups, key=lambda item: (-len(item["proxies"]), item["name"])):
        notes: list[str] = []
        if group["type"] == "url-test" and len(group["proxies"]) > auto_max:
            notes.append(f"超过上限 {auto_max}")
        if group["name"].startswith(mo.FAILOVER_PREFIX):
            notes.append("故障转移子组")
        if not group["proxies"]:
            notes.append("空组")
        print(
            pad(group["name"], name_width)
            + "  "
            + pad(group["type"], 10)
            + "  "
            + f"{len(group['proxies']):>4}  "
            + "，".join(notes)
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读体检生成的覆盖脚本")
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT, help="要体检的 JS 文件")
    parser.add_argument("--nodes", type=int, default=40, help="每个地区造多少个假节点，默认 40")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是表格")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact = args.artifact.expanduser()
    if not artifact.exists():
        print(
            f"找不到要体检的文件: {artifact}\n先生成一次：python merge_override.py --offline",
            file=sys.stderr,
        )
        return 1
    try:
        summary = run_artifact(artifact, max(1, args.nodes))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    problems = inspect(summary, mo.DEFAULT_AUTO_SELECT_MAX)
    if args.json:
        print(
            json.dumps(
                {"groups": summary["groups"], "problems": problems},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_table(summary, mo.DEFAULT_AUTO_SELECT_MAX)
        print()
        if problems:
            print("发现问题：")
            for item in problems:
                print(f"  - {item}")
        else:
            print("没发现问题：没有空组、没有重名、也没混进入口类条目")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
