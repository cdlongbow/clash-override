#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import NamedTuple

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

MATCH_TYPES = frozenset({"MATCH", "FINAL"})
RULE_TYPES = frozenset(
    {
        "DOMAIN",
        "DOMAIN-SUFFIX",
        "DOMAIN-KEYWORD",
        "DOMAIN-REGEX",
        "GEOSITE",
        "GEOIP",
        "IP-CIDR",
        "IP-CIDR6",
        "SRC-IP-CIDR",
        "SRC-IP-CIDR6",
        "IP-SUFFIX",
        "DST-PORT",
        "SRC-PORT",
        "PROCESS",
        "PROCESS-NAME",
        "RULE-SET",
        "NETWORK",
        "IN-TYPE",
        "UID",
        "SUB-RULE",
        *MATCH_TYPES,
    }
)
TYPE_HINTS = "DOMAIN / DOMAIN-SUFFIX / DOMAIN-KEYWORD / GEOSITE / GEOIP / IP-CIDR / MATCH"
BUILTIN_POLICIES = frozenset(
    {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}
)
FAILOVER_PREFIX = "故障转移-"
SCRIPT_MARKER = "function main(config)"
CACHE_WARN_DAYS = 7
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
DEFAULT_DROP_PROXY_TYPES = ('direct', 'reject', 'reject-drop', 'pass', 'compatible')
DEFAULT_DROP_NAME_TOKENS = (
    '\u76f4\u8fde',
    '\u62d2\u7edd',
    '\u653e\u884c',
    '\u5c4f\u853d',
    '\u62e6\u622a',
    'direct',
    'reject',
    'pass',
    'compatible',
)
OTHER_GROUP_TYPES = ('url-test', 'select')
OTHER_GROUP_OLD = "      type: 'select',\n      proxies: otherProxies,"
OTHER_GROUP_URL_TEST_NEW = (
    "      type: 'url-test',\n      tolerance: 50,\n      proxies: otherNodeNames,"
)
OTHER_GROUP_SELECT_NEW = "      type: 'select',\n      proxies: otherNodeNames,"
OTHER_PROXIES_GUARD_OLD = 'otherProxies.length > 0'
OTHER_PROXIES_GUARD_NEW = 'otherNodeNames.length > 0'
OTHER_PROXIES_GUARD_COUNT = 2

POLICY_NAME_PATTERN = re.compile(r"""name:\s*'([^']+)'|name:\s*"([^"]+)\"""")


FAILOVER_GUARD = "...(fallbackGroupNames.length > 0 ? ['故障转移'] : [])"


def _with_guard(prefix: str, suffix: str) -> str:
    """把「故障转移组存在时才挂上」的守卫插进策略列表，避免四处各写一遍。"""
    return f"{prefix}{FAILOVER_GUARD}, {suffix}"

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

  const dropProxyTypes = @@DROP_TYPES@@
  const dropNameTokens = @@DROP_TOKENS@@
  const excludedProxyNames = {}
  const markExcluded = (name) => {
    if (typeof name === 'string' && name.length > 0) {
      excludedProxyNames[name] = true
    }
  }
  for (let i = 0; i < proxies.length; i++) {
    const item = proxies[i]
    const name = item && typeof item.name === 'string' ? item.name : ''
    if (!name) {
      continue
    }
    const type = item && typeof item.type === 'string' ? item.type.toLowerCase() : ''
    if (dropProxyTypes.indexOf(type) >= 0) {
      markExcluded(name)
    }
    const firstToken = name.trim().toLowerCase().split(/[|\/\-_.,:]+/)[0]
    for (let d = 0; d < dropNameTokens.length; d++) {
      if (firstToken === dropNameTokens[d]) {
        markExcluded(name)
      }
    }
  }

  const usableProxyNames = allProxyNames.filter(
    (n) =>
      !excludedProxyNames[n] &&
      n !== '直连' &&
      n !== '拒绝' &&
      !n.includes('中国') &&
      !n.includes('CN') &&
      !n.includes('China') &&
      !n.includes('未知')
  )

  const otherNodeNames = otherProxies.filter((n) => !excludedProxyNames[n])

  const generatedRegionGroups = []"""

FUNCTIONAL_GROUPS_OLD = "  const functionalGroups = []"
FUNCTIONAL_GROUPS_NEW = """  const functionalGroups = []

  functionalGroups.push({
    ...groupBaseOption,
    name: '自动选择',
    type: 'url-test',
    tolerance: 50,
    proxies: autoSelectProxies.length > 0 ? autoSelectProxies : ['直连'],
    icon: 'https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Available.png',
  })

  const fallbackGroups = []
  const fallbackGroupNames = []
  generatedRegionGroups.forEach((g) => {
    if (Array.isArray(g.proxies) && g.proxies.length > 1) {
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

AUTO_SELECT_LIMIT_JS = """  const autoSelectMax = @@AUTO_MAX@@
  const autoSelectProxies = (function () {
    if (!(autoSelectMax > 0) || usableProxyNames.length <= autoSelectMax) {
      return usableProxyNames
    }
    const groupKeys = Object.keys(regionGroups)
    const ownerOf = {}
    for (let k = 0; k < groupKeys.length; k++) {
      const list = regionGroups[groupKeys[k]].proxies
      for (let i = 0; i < list.length; i++) {
        if (ownerOf[list[i]] === undefined) {
          ownerOf[list[i]] = groupKeys[k]
        }
      }
    }
    const owners = []
    const buckets = {}
    for (let i = 0; i < usableProxyNames.length; i++) {
      const name = usableProxyNames[i]
      const owner = ownerOf[name] === undefined ? '_' : ownerOf[name]
      if (!buckets[owner]) {
        buckets[owner] = []
        owners.push(owner)
      }
      buckets[owner].push(name)
    }
    const cursor = {}
    const picked = []
    let added = true
    while (picked.length < autoSelectMax && added) {
      added = false
      for (let o = 0; o < owners.length; o++) {
        const list = buckets[owners[o]]
        const at = cursor[owners[o]] || 0
        if (at < list.length) {
          cursor[owners[o]] = at + 1
          picked.push(list[at])
          added = true
          if (picked.length >= autoSelectMax) {
            break
          }
        }
      }
    }
    return picked.length > 0 ? picked : usableProxyNames.slice(0, autoSelectMax)
  })()
"""


def render_all_proxy_names_js(options: MergeOptions) -> str:
    """把要剔除的代理类型与名称前缀渲染进排除表构造逻辑。"""
    return (
        ALL_PROXY_NAMES_NEW.replace("@@DROP_TYPES@@", json.dumps(list(options.drop_proxy_types)))
        .replace("@@DROP_TOKENS@@", json.dumps(list(options.drop_name_tokens), ensure_ascii=False))
    )


def render_functional_groups_js(options: MergeOptions) -> str:
    """把节点数上限渲染进「自动选择」组的取样逻辑，0 表示不设上限。"""
    head, _, tail = FUNCTIONAL_GROUPS_NEW.partition("\n")
    limited = AUTO_SELECT_LIMIT_JS.replace("@@AUTO_MAX@@", str(options.auto_select_max))
    return head + "\n" + limited + "\n" + tail


DEFAULT_AUTO_SELECT_MAX = 80

DEFAULT_NODE_OLD = "proxies: [...regionGroupNames, '其他节点', '直连']"
DEFAULT_NODE_NEW = _with_guard("proxies: ['自动选择', ", "...regionGroupNames, '其他节点', '直连']")

GROUP_PROXIES_DEFAULT_OLD = "groupProxies = ['默认节点', ...regionGroupNames, '直连']"
GROUP_PROXIES_DEFAULT_NEW = _with_guard("groupProxies = ['自动选择', ", "'默认节点', ...regionGroupNames, '直连']")

GROUP_PROXIES_MEDIA_OLD = "groupProxies = ['默认节点', '直连', ...regionGroupNames]"
GROUP_PROXIES_MEDIA_NEW = _with_guard("groupProxies = ['自动选择', ", "'默认节点', '直连', ...regionGroupNames]")

OTHER_NET_OLD = "proxies: ['默认节点', '国内网站', ...regionGroupNames]"
OTHER_NET_NEW = _with_guard("proxies: ['自动选择', ", "'默认节点', '国内网站', ...regionGroupNames]")


class MergeError(RuntimeError):
    pass


class RuleConfig(NamedTuple):
    rules: list[str]
    allowed_policies: frozenset[str]
    auto_select_max: int | None
    expected_sha256: frozenset[str]
    other_group_type: str | None
    drop_proxy_types: tuple[str, ...] | None
    drop_name_tokens: tuple[str, ...] | None


class MergeOptions(NamedTuple):
    auto_select_max: int = DEFAULT_AUTO_SELECT_MAX
    other_group_type: str = "url-test"
    drop_proxy_types: tuple[str, ...] = DEFAULT_DROP_PROXY_TYPES
    drop_name_tokens: tuple[str, ...] = DEFAULT_DROP_NAME_TOKENS


def read_rules_yaml(path: Path) -> dict:
    if not path.exists():
        raise MergeError(f"找不到规则文件: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MergeError(f"规则文件读取失败: {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MergeError(f"{path} 不是合法 YAML: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise MergeError(f"{path} 顶层必须是键值映射（含 rules 列表）")
    return data


def parse_rules(raw_rules: object, path: Path) -> list[str]:
    if not isinstance(raw_rules, list):
        raise MergeError(f"{path} 缺少 rules 列表")
    cleaned: list[str] = []
    for index, item in enumerate(raw_rules, start=1):
        if not isinstance(item, str) or not item.strip():
            raise MergeError(f"{path} 第 {index} 条规则必须是非空字符串")
        rule = item.strip()
        if "," not in rule:
            raise MergeError(f"{path} 第 {index} 条规则格式无效: {rule}")
        parts = [part.strip() for part in rule.split(",")]
        rule_type = parts[0].upper()
        if rule_type not in RULE_TYPES:
            raise MergeError(
                f"{path} 第 {index} 条规则类型无效: {parts[0]}（常用类型: {TYPE_HINTS}）"
            )
        is_terminator = rule_type in MATCH_TYPES
        fields = 2 if is_terminator else 3
        if len(parts) < fields:
            expected = "类型,策略" if is_terminator else "类型,匹配内容,策略"
            raise MergeError(f"{path} 第 {index} 条规则格式无效，应为 {expected}: {rule}")
        required = ((1, "策略"),) if is_terminator else ((1, "匹配内容"), (2, "策略"))
        for position, label in required:
            if not parts[position]:
                raise MergeError(f"{path} 第 {index} 条规则的{label}为空: {rule}")
        if any(not part for part in parts[3:]):
            raise MergeError(f"{path} 第 {index} 条规则存在空字段: {rule}")
        cleaned.append(rule)
    return cleaned


def parse_allowed_policies(data: dict, path: Path) -> frozenset[str]:
    raw = data.get("allowed_policies")
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise MergeError(f"{path} 的 allowed_policies 必须是字符串列表")
    allowed: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, str) or not item.strip():
            raise MergeError(f"{path} 的 allowed_policies 第 {index} 项必须是非空字符串")
        allowed.add(item.strip())
    return frozenset(allowed)


def normalize_sha256(values: list[str], origin: str) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(values, start=1):
        value = item.strip() if isinstance(item, str) else ""
        if not SHA256_PATTERN.fullmatch(value):
            raise MergeError(f"{origin} 第 {index} 项不是合法的 sha256（64 位十六进制）: {item}")
        result.add(value.lower())
    return result


def parse_auto_select_max(data: dict, path: Path) -> int | None:
    raw = data.get("auto_select_max")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise MergeError(f"{path} 的 auto_select_max 必须是不小于 0 的整数（0 表示不限）")
    return raw


def parse_expected_sha256(data: dict, path: Path) -> frozenset[str]:
    raw = data.get("expected_sha256")
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise MergeError(f"{path} 的 expected_sha256 必须是 sha256 字符串或字符串列表")
    return frozenset(normalize_sha256(raw, f"{path} 的 expected_sha256"))


def parse_drop_list(data: dict, field: str, path: Path) -> tuple[str, ...] | None:
    raw = data.get(field)
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise MergeError(f"{path} 的 {field} 必须是非空字符串列表")
    cleaned: list[str] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, str) or not item.strip():
            raise MergeError(f"{path} 的 {field} 第 {index} 项必须是非空字符串")
        cleaned.append(item.strip().lower())
    return tuple(dict.fromkeys(cleaned))


def parse_other_group_type(data: dict, path: Path) -> str | None:
    raw = data.get("other_group_type")
    if raw is None:
        return None
    if not isinstance(raw, str) or raw.strip() not in OTHER_GROUP_TYPES:
        choices = " / ".join(OTHER_GROUP_TYPES)
        raise MergeError(f"{path} 的 other_group_type 只能是 {choices}: {raw}")
    return raw.strip()


def load_rule_config(path: Path) -> RuleConfig:
    data = read_rules_yaml(path)
    return RuleConfig(
        parse_rules(data.get("rules"), path),
        parse_allowed_policies(data, path),
        parse_auto_select_max(data, path),
        parse_expected_sha256(data, path),
        parse_other_group_type(data, path),
        parse_drop_list(data, "drop_proxy_types", path),
        parse_drop_list(data, "drop_name_tokens", path),
    )


def build_merge_options(args: argparse.Namespace, config: RuleConfig) -> MergeOptions:
    auto_select_max = (
        args.auto_select_max
        if args.auto_select_max is not None
        else (config.auto_select_max if config.auto_select_max is not None else DEFAULT_AUTO_SELECT_MAX)
    )
    if auto_select_max < 0:
        raise MergeError("自动选择组节点上限不能是负数")
    other_group_type = args.other_group_type or config.other_group_type or "url-test"
    if other_group_type not in OTHER_GROUP_TYPES:
        raise MergeError(f"--other-group-type 只能是 {' / '.join(OTHER_GROUP_TYPES)}")
    return MergeOptions(
        auto_select_max=auto_select_max,
        other_group_type=other_group_type,
        drop_proxy_types=config.drop_proxy_types or DEFAULT_DROP_PROXY_TYPES,
        drop_name_tokens=config.drop_name_tokens or DEFAULT_DROP_NAME_TOKENS,
    )


def load_rules(path: Path) -> list[str]:
    return load_rule_config(path).rules


def rule_target(rule: str) -> str:
    """取出规则的目标策略：MATCH/FINAL 在第 2 段，其余类型在第 3 段。"""
    parts = [part.strip() for part in rule.split(",")]
    index = 1 if parts[0].upper() in MATCH_TYPES else 2
    return parts[index]


def collect_defined_policies(script: str) -> set[str]:
    """从产物里静态提取可被规则引用的策略名（策略组 + 内建 reject/direct 节点）。"""
    names = {
        match.group(1) or match.group(2)
        for match in POLICY_NAME_PATTERN.finditer(script)
        if (match.group(1) or match.group(2))
    }
    names |= {f"{FAILOVER_PREFIX}{name}" for name in list(names)}
    names |= set(BUILTIN_POLICIES)
    return names


def validate_rule_targets(script: str, rules: list[str], extra_allowed: set[str]) -> None:
    defined = collect_defined_policies(script) | extra_allowed
    missing: list[str] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules, start=1):
        target = rule_target(rule)
        if target in defined:
            continue
        if target not in seen:
            seen.add(target)
            missing.append(f"  第 {index} 条规则 {rule} 引用了未知策略: {target}")
    if missing:
        sample = ", ".join(sorted(defined, key=lambda n: (len(n), n))[:10])
        raise MergeError(
            "规则目标校验失败（策略在生成的脚本里不存在，Clash 会整体加载失败）:\n"
            + "\n".join(missing)
            + f"\n脚本内可用策略示例: {sample}"
            + "\n若目标来自订阅节点名，请用 allowed_policies 或 --allow-policy 放行；"
            "确认无误可用 --skip-policy-check 跳过校验"
        )


def assert_unique_policy_names(script: str) -> None:
    counter = Counter(
        match.group(1) or match.group(2) for match in POLICY_NAME_PATTERN.finditer(script)
    )
    dups = {name: count for name, count in counter.items() if count > 1}
    if dups:
        detail = "、".join(f"{name} x{count}" for name, count in sorted(dups.items()))
        raise MergeError(
            f"产物中存在重复的策略名，Clash 会拒绝加载: {detail}"
            "（上游脚本可能新增了同名策略组，确认无误可用 --skip-policy-check 跳过）"
        )


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


def replace_exact(
    haystack: str, old: str, new: str, expected: int, label: str
) -> str:
    count = haystack.count(old)
    if count != expected:
        raise MergeError(
            f"替换失败 [{label}]: 期望出现 {expected} 次，实际 {count} 次。远程脚本格式可能已变"
        )
    return haystack.replace(old, new)


class RemoteScript(NamedTuple):
    text: str
    sha256: str
    source: str
    from_cache: bool


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_age_days(path: Path) -> float:
    return max(0.0, (time.time() - path.stat().st_mtime) / 86400.0)


def load_cached_script(cache_path: Path, expected: set[str]) -> RemoteScript:
    text = read_script(cache_path, "缓存文件")
    if SCRIPT_MARKER not in text:
        raise MergeError(f"缓存文件缺少 '{SCRIPT_MARKER}'，已损坏或版本不符: {cache_path}")
    digest = sha256_of(text)
    if expected and digest not in expected:
        raise MergeError(
            f"缓存脚本 sha256 {digest} 与期望值不符: {' '.join(sorted(expected))}"
        )
    age = cache_age_days(cache_path)
    if age > CACHE_WARN_DAYS:
        print(f"警告: 缓存已 {age:.0f} 天未更新，上游脚本可能已变化: {cache_path}")
    else:
        print(f"使用本地缓存（{age:.0f} 天前）: {cache_path}")
    return RemoteScript(text, digest, str(cache_path), True)


def download_remote(
    urls: list[str],
    cache_path: Path,
    timeout: int = REQUEST_TIMEOUT,
    expected_sha256: set[str] | None = None,
) -> RemoteScript:
    pinned = {value.strip().lower() for value in expected_sha256 or set() if value.strip()}
    net_errors: list[str] = []
    invalid: list[str] = []
    for url in urls:
        print(f"正在下载远程脚本: {url}")
        try:
            resp = requests.get(url, timeout=timeout, headers=REQUEST_HEADERS)
            resp.raise_for_status()
            text = resp.text
        except Exception as exc:
            net_errors.append(f"{url}: {exc}")
            print(f"网络失败，尝试下一个源: {exc}")
            continue
        digest = sha256_of(text)
        if SCRIPT_MARKER not in text:
            invalid.append(f"{url}: 内容缺少 '{SCRIPT_MARKER}'，sha256 {digest[:12]}")
            print(f"内容不像 YaNet 覆盖脚本，尝试下一个源: {url}")
            continue
        if pinned and digest not in pinned:
            invalid.append(f"{url}: sha256 {digest} 与期望值不符")
            print(f"sha256 校验不通过，尝试下一个源: {url}")
            continue
        try:
            cache_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"缓存写入失败（不影响本次合并）: {exc}")
        print(f"下载成功，脚本长度: {len(text)}，sha256: {digest}")
        return RemoteScript(text, digest, url, False)
    if cache_path.exists():
        print("所有远程源失败，回退本地缓存")
        return load_cached_script(cache_path, pinned)
    detail: list[str] = []
    if net_errors:
        detail.append("网络失败:\n  " + "\n  ".join(net_errors))
    if invalid:
        detail.append("内容校验失败:\n  " + "\n  ".join(invalid))
    if not detail:
        detail.append("未配置任何下载源")
    raise MergeError("下载远程脚本失败:\n" + "\n".join(detail))


def merge_script(
    remote_code: str,
    rules: list[str],
    options: MergeOptions | None = None,
) -> str:
    opts = options or MergeOptions()
    match = ENABLE_PATTERN.search(remote_code)
    if not match:
        raise MergeError("未找到 'if (!enable) return config' 语句，脚本格式可能已变")

    combined = remote_code[: match.end()] + build_custom_rules_js(rules) + remote_code[match.end() :]
    combined = replace_once(
        combined, ALL_PROXY_NAMES_OLD, render_all_proxy_names_js(opts), "allProxyNames"
    )
    combined = replace_once(
        combined,
        FUNCTIONAL_GROUPS_OLD,
        render_functional_groups_js(opts),
        "functionalGroups",
    )
    combined = replace_once(combined, DEFAULT_NODE_OLD, DEFAULT_NODE_NEW, "默认节点 proxies")
    combined = replace_once(combined, GROUP_PROXIES_DEFAULT_OLD, GROUP_PROXIES_DEFAULT_NEW, "服务组 proxies")
    combined = replace_once(combined, GROUP_PROXIES_MEDIA_OLD, GROUP_PROXIES_MEDIA_NEW, "港澳台媒体 proxies")
    combined = replace_once(combined, OTHER_NET_OLD, OTHER_NET_NEW, "其他外网 proxies")
    other_group_new = (
        OTHER_GROUP_URL_TEST_NEW
        if opts.other_group_type == "url-test"
        else OTHER_GROUP_SELECT_NEW
    )
    combined = replace_once(combined, OTHER_GROUP_OLD, other_group_new, "其他节点 group")
    combined = replace_exact(
        combined,
        OTHER_PROXIES_GUARD_OLD,
        OTHER_PROXIES_GUARD_NEW,
        OTHER_PROXIES_GUARD_COUNT,
        "其他节点 判空守卫",
    )
    return combined


def path_arg(raw: str) -> Path:
    return Path(raw).expanduser()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="拉取 YaNet 脚本并注入自定义分流规则")
    parser.add_argument(
        "--rules",
        type=path_arg,
        default=DEFAULT_RULES,
        help="自定义规则 YAML 路径（默认值锚定脚本目录，传入相对路径按当前目录解析）",
    )
    parser.add_argument("--output", type=path_arg, default=DEFAULT_OUTPUT, help="输出 JS 路径")
    parser.add_argument("--cache", type=path_arg, default=CACHE_PATH, help="远程脚本缓存路径")
    parser.add_argument("--offline", action="store_true", help="只使用本地缓存，不访问网络")
    parser.add_argument(
        "--allow-policy",
        action="append",
        default=[],
        metavar="NAME",
        help="额外放行的目标策略名（订阅里的节点名等），可重复使用",
    )
    parser.add_argument(
        "--skip-policy-check",
        action="store_true",
        help="跳过规则目标策略组与产物策略名校验",
    )
    parser.add_argument(
        "--auto-select-max",
        type=int,
        default=None,
        metavar="N",
        help=f"自动选择组的节点数上限，0 表示不限，默认 {DEFAULT_AUTO_SELECT_MAX}",
    )
    parser.add_argument(
        "--other-group-type",
        choices=OTHER_GROUP_TYPES,
        default=None,
        help="其他节点组类型，默认 url-test（自动测速），可设回 select 手动选",
    )
    parser.add_argument(
        "--expect-sha256",
        action="append",
        default=[],
        metavar="HEX",
        help="上游脚本 sha256 期望值，可重复使用；全部不匹配时报错",
    )
    return parser.parse_args(argv)


def read_script(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MergeError(f"{label}读取失败: {path}: {exc}") from exc


def write_output(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise MergeError(f"输出文件写入失败: {path}（请确认父目录存在且可写）: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_rule_config(args.rules)
        rules = config.rules
        print(f"已加载 {len(rules)} 条自定义规则: {args.rules}")
        options = build_merge_options(args, config)
        cli_hashes = normalize_sha256(args.expect_sha256, "--expect-sha256")
        pinned = cli_hashes | set(config.expected_sha256)
        if args.offline:
            if not args.cache.exists():
                raise MergeError(f"--offline 需要缓存文件: {args.cache}")
            script = load_cached_script(args.cache, pinned)
        else:
            script = download_remote(REMOTE_URLS, args.cache, expected_sha256=pinned)
        print(f"上游脚本: {script.source}，sha256 {script.sha256}，长度 {len(script.text)}")
        combined = merge_script(script.text, rules, options)
        if args.skip_policy_check:
            print("已跳过产物策略名校验")
        else:
            extra = {name.strip() for name in args.allow_policy if name.strip()}
            validate_rule_targets(combined, rules, extra | set(config.allowed_policies))
            assert_unique_policy_names(combined)
            print("规则目标与策略名唯一性校验通过")
        write_output(args.output, combined)
        limit = f"{options.auto_select_max}" if options.auto_select_max > 0 else "不限"
        print(
            f"合并完成，已保存到: {args.output}，产物 sha256 {sha256_of(combined)}，"
            f"自动选择节点上限 {limit}，其他节点组类型 {options.other_group_type}"
        )
        return 0
    except MergeError as exc:
        print(f"合并出错: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件操作失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
