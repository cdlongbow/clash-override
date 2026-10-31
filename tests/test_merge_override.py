import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import merge_override as mo

FIXTURE = """\
function main(config) {
  if (!enable) return config
  const proxies = config?.proxies || []
  const otherProxies = []
  const regionGroups = {}

  const generatedRegionGroups = []

  if (otherProxies.length > 0) {
    generatedRegionGroups.push({
      ...groupBaseOption,
      name: '其他节点',
      type: 'select',
      proxies: otherProxies,
      icon: 'https://example.com/world.png',
    })
  }

  const functionalGroups = []

  functionalGroups.push({
    name: '默认节点',
    type: 'select',
    proxies: [...regionGroupNames, '其他节点', '直连'].filter((n) => n !== '其他节点' || otherProxies.length > 0),
  })

  if (svc.reject) {
    groupProxies = ['拒绝', '直连', '默认节点']
  } else if (svc.key === 'biliintl' || svc.key === 'bahamut') {
    groupProxies = ['默认节点', '直连', ...regionGroupNames]
  } else {
    groupProxies = ['默认节点', ...regionGroupNames, '直连']
  }

  functionalGroups.push(
    {
      name: '其他外网',
      type: 'select',
      proxies: ['默认节点', '国内网站', ...regionGroupNames],
    }
  )
  return config
}
"""


def test_load_rules(tmp_path: Path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        yaml.safe_dump(
            {"rules": ["DOMAIN-SUFFIX,example.com,DIRECT", "DOMAIN-KEYWORD,dmm,JP日本"]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert mo.load_rules(path) == [
        "DOMAIN-SUFFIX,example.com,DIRECT",
        "DOMAIN-KEYWORD,dmm,JP日本",
    ]


def test_load_rules_rejects_invalid(tmp_path: Path):
    path = tmp_path / "rules.yaml"
    path.write_text("rules:\n  - bad-rule\n", encoding="utf-8")
    with pytest.raises(mo.MergeError, match="格式无效"):
        mo.load_rules(path)


def test_build_custom_rules_js_preserves_order():
    js = mo.build_custom_rules_js(["DOMAIN-SUFFIX,a.com,DIRECT", "DOMAIN-SUFFIX,b.com,US美国"])
    assert "rules.unshift(" in js
    assert js.index("a.com") < js.index("b.com")


def test_replace_once_requires_single_hit():
    with pytest.raises(mo.MergeError, match="实际 0 次"):
        mo.replace_once("abc", "zzz", "yyy", "missing")
    with pytest.raises(mo.MergeError, match="实际 2 次"):
        mo.replace_once("aba", "a", "x", "dup")
    assert mo.replace_once("abc", "b", "B", "ok") == "aBc"


def test_merge_script_injects_groups_and_rules():
    rules = ["DOMAIN-SUFFIX,example.com,DIRECT"]
    out = mo.merge_script(FIXTURE, rules)
    assert 'rules.unshift(\n    "DOMAIN-SUFFIX,example.com,DIRECT"\n  )' in out
    assert "const usableProxyNames = allProxyNames.filter" in out
    assert "name: '自动选择'" in out
    assert "autoSelectProxies.length > 0 ? autoSelectProxies" in out
    assert "const autoSelectMax = 80" in out
    assert "fallbackGroups.push" in out
    assert "generatedRegionGroups.push(fallbackGroups[i])" in out
    assert "...(fallbackGroupNames.length > 0 ? ['故障转移'] : [])" in out
    assert out.count("const functionalGroups = []") == 1
    assert "proxies: [...regionGroupNames, '其他节点', '直连']" not in out
    assert "groupProxies = ['默认节点', ...regionGroupNames, '直连']" not in out


def test_merge_script_fails_when_anchor_missing():
    with pytest.raises(mo.MergeError, match="if \\(!enable\\)"):
        mo.merge_script("function main() {}", [])


def test_real_custom_rules_file():
    rules = mo.load_rules(Path(__file__).resolve().parents[1] / "custom_rules.yaml")
    assert len(rules) >= 1
    assert all(r.count(",") >= 2 for r in rules)


def test_download_uses_cache_when_all_urls_fail(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache.js"
    cache.write_text("function main(config) {}", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(mo.requests, "get", boom)
    script = mo.download_remote(["https://example.invalid/script.js"], cache)
    assert script.text == "function main(config) {}"
    assert script.from_cache is True
    assert script.source == str(cache)


def test_download_rejects_non_script(monkeypatch, tmp_path: Path):
    class FakeResp:
        text = "not a clash script"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(mo.requests, "get", lambda *_args, **_kwargs: FakeResp())
    cache = tmp_path / "cache.js"
    with pytest.raises(mo.MergeError, match="下载远程脚本失败"):
        mo.download_remote(["https://example.invalid/script.js"], cache)


RULE_OK = "DOMAIN-SUFFIX,a.com,DIRECT"


def write_yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_rules_rejects_unknown_type(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - " + RULE_OK.replace("DOMAIN", "FOO-TYPE") + "\n")
    with pytest.raises(mo.MergeError, match="类型无效"):
        mo.load_rules(path)


def test_load_rules_accepts_lowercase_type(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - domain-suffix,a.com,DIRECT\n")
    assert mo.load_rules(path) == ["domain-suffix,a.com,DIRECT"]


def test_load_rules_rejects_missing_target(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com\n")
    with pytest.raises(mo.MergeError, match="格式无效"):
        mo.load_rules(path)


def test_load_rules_rejects_empty_fields(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - DOMAIN-SUFFIX,,DIRECT\n")
    with pytest.raises(mo.MergeError, match="匹配内容为空"):
        mo.load_rules(path)
    path = write_yaml(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,\n")
    with pytest.raises(mo.MergeError, match="策略为空"):
        mo.load_rules(path)


def test_load_rules_accepts_match_without_payload(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - MATCH,其他外网\n")
    assert mo.load_rules(path) == ["MATCH,其他外网"]


def test_load_rules_rejects_match_without_target(tmp_path: Path):
    path = write_yaml(tmp_path, "rules:\n  - MATCH,\n")
    with pytest.raises(mo.MergeError, match="策略为空"):
        mo.load_rules(path)


def test_load_rules_reports_yaml_error(tmp_path: Path):
    path = write_yaml(tmp_path, "rules: [unclosed\n")
    with pytest.raises(mo.MergeError, match="不是合法 YAML"):
        mo.load_rules(path)


def test_load_rules_rejects_non_mapping_document(tmp_path: Path):
    path = write_yaml(tmp_path, "- DOMAIN-SUFFIX,a.com,DIRECT\n")
    with pytest.raises(mo.MergeError, match="顶层必须是键值映射"):
        mo.load_rules(path)


def test_load_rule_config_reads_allowed_policies(tmp_path: Path):
    path = write_yaml(
        tmp_path,
        "rules:\n  - DOMAIN-SUFFIX,a.com,My-Node\nallowed_policies:\n  - My-Node\n",
    )
    config = mo.load_rule_config(path)
    assert config.rules == ["DOMAIN-SUFFIX,a.com,My-Node"]
    assert config.allowed_policies == frozenset({"My-Node"})


def test_load_rule_config_rejects_bad_allowed_policies(tmp_path: Path):
    text = "rules:\n  - " + RULE_OK + "\nallowed_policies:\n  a: 1\n"
    path = write_yaml(tmp_path, text)
    with pytest.raises(mo.MergeError, match="allowed_policies 必须是字符串列表"):
        mo.load_rule_config(path)


def test_rule_target_position_depends_on_type():
    assert mo.rule_target("IP-CIDR,1.2.3.4/32,自动选择,no-resolve") == "自动选择"
    assert mo.rule_target("MATCH,其他外网") == "其他外网"


def test_validate_rule_targets_accepts_script_policies():
    merged = mo.merge_script(FIXTURE, ["DOMAIN-SUFFIX,a.com,默认节点"])
    mo.validate_rule_targets(
        merged,
        [
            "DOMAIN-SUFFIX,a.com,默认节点",
            "DOMAIN-SUFFIX,b.com,自动选择",
            "DOMAIN-SUFFIX,c.com,故障转移-默认节点",
            "DOMAIN-SUFFIX,d.com,DIRECT",
            "IP-CIDR,1.1.1.1/32,其他外网,no-resolve",
        ],
        set(),
    )


def test_validate_rule_targets_rejects_unknown_policy():
    merged = mo.merge_script(FIXTURE, [])
    with pytest.raises(mo.MergeError, match="US美国"):
        mo.validate_rule_targets(merged, ["DOMAIN-SUFFIX,a.com,US美国"], set())


def test_validate_rule_targets_reports_every_missing_policy_once():
    merged = mo.merge_script(FIXTURE, [])
    with pytest.raises(mo.MergeError, match="未知策略") as exc:
        mo.validate_rule_targets(
            merged,
            [
                "DOMAIN-SUFFIX,a.com,不存在A",
                "DOMAIN-SUFFIX,b.com,不存在A",
                "DOMAIN-SUFFIX,c.com,不存在B",
            ],
            set(),
        )
    message = str(exc.value)
    assert message.count("不存在A") == 2
    assert "不存在B" in message


def test_validate_rule_targets_honours_extra_allowed():
    merged = mo.merge_script(FIXTURE, [])
    mo.validate_rule_targets(
        merged,
        ["DOMAIN-SUFFIX,a.com,My-Node"],
        {"My-Node"},
    )


def run_offline_main(tmp_path: Path, rules_text: str, output: Path) -> int:
    cache = tmp_path / "cache.js"
    cache.write_text(FIXTURE, encoding="utf-8")
    rules = write_yaml(tmp_path, rules_text)
    return mo.main(
        ["--offline", "--rules", str(rules), "--cache", str(cache), "--output", str(output)]
    )


def test_main_offline_writes_validated_output(tmp_path: Path):
    output = tmp_path / "out.js"
    code = run_offline_main(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,默认节点\n", output)
    assert code == 0
    text = output.read_text(encoding="utf-8")
    assert "DOMAIN-SUFFIX,a.com,默认节点" in text
    assert "name: '自动选择'" in text


def test_main_fails_on_unknown_policy(tmp_path: Path):
    output = tmp_path / "out.js"
    code = run_offline_main(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,不存在的组\n", output)
    assert code == 1
    assert not output.exists()


def test_main_allow_policy_flag(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text(FIXTURE, encoding="utf-8")
    rules = write_yaml(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,My-Node\n")
    output = tmp_path / "out.js"
    code = mo.main(
        [
            "--offline",
            "--rules",
            str(rules),
            "--cache",
            str(cache),
            "--output",
            str(output),
            "--allow-policy",
            "My-Node",
        ]
    )
    assert code == 0
    assert output.exists()


def test_main_skip_policy_check(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text(FIXTURE, encoding="utf-8")
    rules = write_yaml(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,My-Node\n")
    output = tmp_path / "out.js"
    code = mo.main(
        [
            "--offline",
            "--rules",
            str(rules),
            "--cache",
            str(cache),
            "--output",
            str(output),
            "--skip-policy-check",
        ]
    )
    assert code == 0
    assert output.exists()


def test_main_reports_unwritable_output(tmp_path: Path):
    output = tmp_path / "missing-dir" / "out.js"
    code = run_offline_main(tmp_path, "rules:\n  - DOMAIN-SUFFIX,a.com,默认节点\n", output)
    assert code == 1


def test_main_reports_missing_rules_file(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text(FIXTURE, encoding="utf-8")
    code = mo.main(
        [
            "--offline",
            "--rules",
            str(tmp_path / "nope.yaml"),
            "--cache",
            str(cache),
            "--output",
            str(tmp_path / "out.js"),
        ]
    )
    assert code == 1


class ScriptResp:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


SCRIPT_BODY = "function main(config) {\n  return config\n}\n"


def test_build_custom_rules_js_handles_empty_rules():
    assert "自定义优先规则：无" in mo.build_custom_rules_js([])


def test_download_returns_digest_and_writes_cache(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mo.requests, "get", lambda *_a, **_k: ScriptResp(SCRIPT_BODY))
    cache = tmp_path / "cache.js"
    script = mo.download_remote(["https://example.invalid/a.js"], cache)
    assert script.sha256 == mo.sha256_of(SCRIPT_BODY)
    assert script.from_cache is False
    assert script.source == "https://example.invalid/a.js"
    assert cache.read_text(encoding="utf-8") == SCRIPT_BODY


def test_download_separates_content_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mo.requests, "get", lambda *_a, **_k: ScriptResp("nope"))
    with pytest.raises(mo.MergeError, match="内容校验失败") as exc:
        mo.download_remote(["https://example.invalid/a.js"], tmp_path / "cache.js")
    assert "网络失败" not in str(exc.value)


def test_download_accepts_pinned_sha256(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mo.requests, "get", lambda *_a, **_k: ScriptResp(SCRIPT_BODY))
    script = mo.download_remote(
        ["https://example.invalid/a.js"],
        tmp_path / "cache.js",
        expected_sha256={mo.sha256_of(SCRIPT_BODY).upper()},
    )
    assert script.sha256 == mo.sha256_of(SCRIPT_BODY)


def test_download_rejects_unpinned_sha256(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mo.requests, "get", lambda *_a, **_k: ScriptResp(SCRIPT_BODY))
    with pytest.raises(mo.MergeError, match="sha256") as exc:
        mo.download_remote(
            ["https://example.invalid/a.js"],
            tmp_path / "cache.js",
            expected_sha256={"0" * 64},
        )
    assert "内容校验失败" in str(exc.value)


def test_cached_script_rejects_corrupted_cache(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text("console.log(1)\n", encoding="utf-8")
    with pytest.raises(mo.MergeError, match="缓存文件缺少"):
        mo.load_cached_script(cache, set())


def test_cached_script_rejects_sha_mismatch(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text(SCRIPT_BODY, encoding="utf-8")
    with pytest.raises(mo.MergeError, match="与期望值不符"):
        mo.load_cached_script(cache, {"0" * 64})


def test_load_rule_config_parses_new_keys(tmp_path: Path):
    digest = "ab" * 32
    text = (
        "rules:\n  - " + RULE_OK + "\nauto_select_max: 30\nexpected_sha256:\n  - " + digest + "\n"
    )
    config = mo.load_rule_config(write_yaml(tmp_path, text))
    assert config.auto_select_max == 30
    assert config.expected_sha256 == frozenset({"ab" * 32})


def test_load_rule_config_rejects_bad_auto_select_max(tmp_path: Path):
    text = "rules:\n  - " + RULE_OK + "\nauto_select_max: -1\n"
    with pytest.raises(mo.MergeError, match="auto_select_max"):
        mo.load_rule_config(write_yaml(tmp_path, text))


def test_load_rule_config_rejects_bad_expected_sha256(tmp_path: Path):
    text = "rules:\n  - " + RULE_OK + "\nexpected_sha256:\n  - not-hex\n"
    with pytest.raises(mo.MergeError, match="sha256（64 位十六进制）"):
        mo.load_rule_config(write_yaml(tmp_path, text))


def test_merge_script_renders_auto_select_limit():
    limited = mo.merge_script(FIXTURE, [], mo.MergeOptions(auto_select_max=12))
    assert "const autoSelectMax = 12" in limited
    assert "const autoSelectMax = 80" not in limited


def test_auto_select_sampling_and_proxy_exclusion():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    r1 = [f"R1 node {i}" for i in range(1, 61)]
    r2 = [f"R2 node {i}" for i in range(1, 41)]
    options = mo.MergeOptions(auto_select_max=20)
    js = (
        "const groupBaseOption = {}\n"
        "const regionGroups = { R1: { proxies: "
        + json.dumps(r1 + ["\u76f4\u8fde|\u53cc\u7ebf"], ensure_ascii=False)
        + " }, R2: { proxies: "
        + json.dumps(r2, ensure_ascii=False)
        + " } }\n"
        "const otherProxies = "
        + json.dumps(
            ["Extra-1", "\u76f4\u8fde|\u4ec5IPv4", "Gateway Ad"], ensure_ascii=False
        )
        + "\n"
        "const proxies = "
        + json.dumps(
            [
                {"name": "\u76f4\u8fde|\u53cc\u7ebf", "type": "vless"},
                {"name": "\u76f4\u8fde|\u4ec5IPv4", "type": "vless"},
                {"name": "Gateway Ad", "type": "direct"},
            ],
            ensure_ascii=False,
        )
        + "\n"
        + mo.render_all_proxy_names_js(options)
        + "\n"
        + mo.render_functional_groups_js(options)
        + "\nconsole.log(JSON.stringify({ auto: autoSelectProxies, other: otherNodeNames }))\n"
    )
    raw = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    picked = json.loads(raw.strip().splitlines()[-1])
    auto = picked["auto"]
    assert len(auto) == 20
    assert len([n for n in auto if n.startswith("R1")]) >= 8
    assert len([n for n in auto if n.startswith("R2")]) >= 8
    assert all("\u76f4\u8fde" not in n for n in auto)
    assert picked["other"] == ["Extra-1"]
def test_assert_unique_policy_names_rejects_duplicate():
    script = "name: '默认节点',\nname: '默认节点',\nname: '其他外网',"
    with pytest.raises(mo.MergeError, match="重复的策略名"):
        mo.assert_unique_policy_names(script)
    mo.assert_unique_policy_names("name: '默认节点',\nname: '其他外网',")


def test_main_cli_auto_select_max_overrides_yaml(tmp_path: Path):
    cache = tmp_path / "cache.js"
    cache.write_text(FIXTURE, encoding="utf-8")
    rules = write_yaml(tmp_path, "rules:\n  - " + RULE_OK + "\nauto_select_max: 30\n")
    output = tmp_path / "out.js"
    code = mo.main(
        [
            "--offline",
            "--rules",
            str(rules),
            "--cache",
            str(cache),
            "--output",
            str(output),
            "--auto-select-max",
            "0",
        ]
    )
    assert code == 0
    assert "const autoSelectMax = 0" in output.read_text(encoding="utf-8")


def test_load_rule_config_parses_group_and_drop_options(tmp_path: Path):
    text = (
        "rules:\n  - "
        + RULE_OK
        + "\nother_group_type: select\ndrop_proxy_types:\n  - Dumb\ndrop_name_tokens:\n  - AD\n"
    )
    config = mo.load_rule_config(write_yaml(tmp_path, text))
    assert config.other_group_type == "select"
    assert config.drop_proxy_types == ("dumb",)
    assert config.drop_name_tokens == ("ad",)


def test_load_rule_config_rejects_bad_other_group_type(tmp_path: Path):
    text = "rules:\n  - " + RULE_OK + "\nother_group_type: fallback\n"
    with pytest.raises(mo.MergeError, match="other_group_type"):
        mo.load_rule_config(write_yaml(tmp_path, text))


def test_other_group_type_select_keeps_manual_choice():
    merged = mo.merge_script(FIXTURE, [], mo.MergeOptions(other_group_type="select"))
    assert "      type: 'select',\n      proxies: otherNodeNames," in merged
    assert "tolerance: 50,\n      proxies: otherNodeNames," not in merged


def test_other_group_type_url_test_by_default():
    merged = mo.merge_script(FIXTURE, [])
    assert "      type: 'url-test',\n      tolerance: 50,\n      proxies: otherNodeNames," in merged


def test_other_nodes_get_failover_group():
    merged = mo.merge_script(FIXTURE, [])
    assert "if (Array.isArray(g.proxies) && g.proxies.length > 1) {" in merged
    assert "otherProxies.length > 0" not in merged
