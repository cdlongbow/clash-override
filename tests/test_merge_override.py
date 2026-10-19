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
    assert "usableProxyNames.length > 0 ? usableProxyNames : ['直连']" in out
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
    text = mo.download_remote(["https://example.invalid/script.js"], cache)
    assert text == "function main(config) {}"


def test_download_rejects_non_script(monkeypatch, tmp_path: Path):
    class FakeResp:
        text = "not a clash script"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(mo.requests, "get", lambda *_args, **_kwargs: FakeResp())
    cache = tmp_path / "cache.js"
    with pytest.raises(mo.MergeError, match="下载远程脚本失败"):
        mo.download_remote(["https://example.invalid/script.js"], cache)
