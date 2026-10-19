#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
DEFAULT_RULES = ROOT / "custom_rules.yaml"
DEFAULT_OUTPUT = ROOT / "my_merged_override.js"
CACHE_PATH = ROOT / ".yanet_cache.js"

REMOTE_URLS = [
    "https://fastly.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js",
    "https://cdn.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js",
    "https://gcore.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js",
    "https://raw.githubusercontent.com/dahaha-365/YaNet/main/Mihomo/global_script.js",
]

ENABLE_PATTERN = re.compile(r"(if\s*\(!enable\)\s*return\s+config\s*;?\s*\n)")
REQUEST_HEADERS = {"User-Agent": "clash-override/1.1"}
REQUEST_TIMEOUT = 15

ALL_PROXY_NAMES_OLD = "  const generatedRegionGroups = []"
ALL_PROXY_NAMES_NEW = """  const allProxyNames = []
  Object.keys(regionGroups).forEach((key) => {
    const list = regionGroups[key].proxies
    for (let i = 0; i < list.length; i++) {
      allProxyNames.push(list[i])
    }
  })
  for (let i = 0; i < otherProxies.length; i++) {
    allProxyNames.push(otherProxies[i])
  }
  const usableProxyNames = allProxyNames.filter(
    (n) =>
      n !== '直连' &&
      n !== '拒绝' &&
      !n.includes('中国') &&
      !n.includes('CN') &&
      !n.includes('China') &&
      !n.includes('未知')
  )

  const generatedRegionGroups = []"""

FUNCTIONAL_GROUPS_OLD = "  const functionalGroups = []"
FUNCTIONAL_GROUPS_NEW = """  const functionalGroups = []

  functionalGroups.push({
    ...groupBaseOption,
    name: '自动选择',
    type: 'url-test',
    tolerance: 50,
    proxies: usableProxyNames.length > 0 ? usableProxyNames : ['直连'],
    icon: 'https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Available.png',
  })

  const fallbackGroups = []
  const fallbackGroupNames = []
  generatedRegionGroups.forEach((g) => {
    if (g.name !== '其他节点' && Array.isArray(g.proxies) && g.proxies.length > 1) {
      const fbName = '故障转移-' + g.name
      fallbackGroupNames.push(fbName)
      fallbackGroups.push({
        ...groupBaseOption,
        name: fbName,
        type: 'fallback',
        url: 'https://www.gstatic.com/generate_204',
        proxies: g.proxies,
        icon: g.icon,
      })
    }
  })
  for (let i = 0; i < fallbackGroups.length; i++) {
    generatedRegionGroups.push(fallbackGroups[i])
  }

  if (fallbackGroupNames.length > 0) {
    functionalGroups.push({
      ...groupBaseOption,
      name: '故障转移',
      type: 'select',
      proxies: fallbackGroupNames,
      icon: 'https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Global.png',
    })
  }
"""

DEFAULT_NODE_OLD = "proxies: [...regionGroupNames, '其他节点', '直连']"
DEFAULT_NODE_NEW = (
    "proxies: ['自动选择', ...(fallbackGroupNames.length > 0 ? ['故障转移'] : []), "
    "...regionGroupNames, '其他节点', '直连']"
)

GROUP_PROXIES_DEFAULT_OLD = "groupProxies = ['默认节点', ...regionGroupNames, '直连']"
GROUP_PROXIES_DEFAULT_NEW = (
    "groupProxies = ['自动选择', ...(fallbackGroupNames.length > 0 ? ['故障转移'] : []), "
    "'默认节点', ...regionGroupNames, '直连']"
)

GROUP_PROXIES_MEDIA_OLD = "groupProxies = ['默认节点', '直连', ...regionGroupNames]"
GROUP_PROXIES_MEDIA_NEW = (
    "groupProxies = ['自动选择', ...(fallbackGroupNames.length > 0 ? ['故障转移'] : []), "
    "'默认节点', '直连', ...regionGroupNames]"
)

OTHER_NET_OLD = "proxies: ['默认节点', '国内网站', ...regionGroupNames]"
OTHER_NET_NEW = (
    "proxies: ['自动选择', ...(fallbackGroupNames.length > 0 ? ['故障转移'] : []), "
    "'默认节点', '国内网站', ...regionGroupNames]"
)


class MergeError(RuntimeError):
    pass


def load_rules(path: Path) -> list[str]:
    if not path.exists():
        raise MergeError(f"找不到规则文件: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = data.get("rules")
    if not isinstance(rules, list):
        raise MergeError(f"{path} 缺少 rules 列表")
    cleaned: list[str] = []
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, str) or not item.strip():
            raise MergeError(f"{path} 第 {index} 条规则必须是非空字符串")
        rule = item.strip()
        if rule.count(",") < 2:
            raise MergeError(f"{path} 第 {index} 条规则格式无效: {rule}")
        cleaned.append(rule)
    return cleaned


def build_custom_rules_js(rules: list[str]) -> str:
    if not rules:
        return "\n  // === 用户自定义优先规则：无 ===\n"
    items = ",\n".join(f"    {json.dumps(rule, ensure_ascii=False)}" for rule in rules)
    return (
        "\n  // === 以下为用户自定义优先规则 ===\n"
        f"  rules.unshift(\n{items}\n  )\n"
        "  // === 自定义规则结束 ===\n"
    )


def replace_once(haystack: str, old: str, new: str, label: str) -> str:
    count = haystack.count(old)
    if count != 1:
        raise MergeError(f"替换失败 [{label}]: 期望出现 1 次，实际 {count} 次。远程脚本格式可能已变")
    return haystack.replace(old, new, 1)


def download_remote(urls: list[str], cache_path: Path, timeout: int = REQUEST_TIMEOUT) -> str:
    errors: list[str] = []
    for url in urls:
        try:
            print(f"正在下载远程脚本: {url}")
            resp = requests.get(url, timeout=timeout, headers=REQUEST_HEADERS)
            resp.raise_for_status()
            text = resp.text
            if "function main(config)" not in text:
                raise MergeError("下载内容不像 YaNet 覆盖脚本")
            cache_path.write_text(text, encoding="utf-8")
            print(f"下载成功，脚本长度: {len(text)}")
            return text
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            print(f"下载失败，尝试下一个源: {exc}")
    if cache_path.exists():
        print(f"所有远程源失败，使用本地缓存: {cache_path}")
        return cache_path.read_text(encoding="utf-8")
    raise MergeError("下载远程脚本失败:\n" + "\n".join(errors))


def merge_script(remote_code: str, rules: list[str]) -> str:
    match = ENABLE_PATTERN.search(remote_code)
    if not match:
        raise MergeError("未找到 'if (!enable) return config' 语句，脚本格式可能已变")

    combined = remote_code[: match.end()] + build_custom_rules_js(rules) + remote_code[match.end() :]
    combined = replace_once(combined, ALL_PROXY_NAMES_OLD, ALL_PROXY_NAMES_NEW, "allProxyNames")
    combined = replace_once(combined, FUNCTIONAL_GROUPS_OLD, FUNCTIONAL_GROUPS_NEW, "functionalGroups")
    combined = replace_once(combined, DEFAULT_NODE_OLD, DEFAULT_NODE_NEW, "默认节点 proxies")
    combined = replace_once(combined, GROUP_PROXIES_DEFAULT_OLD, GROUP_PROXIES_DEFAULT_NEW, "服务组 proxies")
    combined = replace_once(combined, GROUP_PROXIES_MEDIA_OLD, GROUP_PROXIES_MEDIA_NEW, "港澳台媒体 proxies")
    combined = replace_once(combined, OTHER_NET_OLD, OTHER_NET_NEW, "其他外网 proxies")
    return combined


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="拉取 YaNet 脚本并注入自定义分流规则")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES, help="自定义规则 YAML 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 JS 路径")
    parser.add_argument("--cache", type=Path, default=CACHE_PATH, help="远程脚本缓存路径")
    parser.add_argument("--offline", action="store_true", help="只使用本地缓存，不访问网络")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rules = load_rules(args.rules)
        print(f"已加载 {len(rules)} 条自定义规则: {args.rules}")
        if args.offline:
            if not args.cache.exists():
                raise MergeError(f"--offline 需要缓存文件: {args.cache}")
            remote_code = args.cache.read_text(encoding="utf-8")
            print(f"离线模式，读取缓存: {args.cache}")
        else:
            remote_code = download_remote(REMOTE_URLS, args.cache)
        combined = merge_script(remote_code, rules)
        args.output.write_text(combined, encoding="utf-8")
        print(f"合并完成，已保存到: {args.output}")
        return 0
    except MergeError as exc:
        print(f"合并出错: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
