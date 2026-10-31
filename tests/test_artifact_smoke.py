import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import merge_override as mo

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "my_merged_override.js"

HARNESS = """
import { readFileSync } from 'fs'
const src = readFileSync(process.env.ARTIFACT_PATH, 'utf8')
const names = []
const seed = [['HK', 3], ['US', 120], ['JP', 4]]
for (const [label, count] of seed) {
  for (let i = 1; i <= count; i++) names.push(label + ' node ' + i + ' | x1.5')
}
for (let i = 1; i <= 5; i++) names.push('Fallback-' + i)
const config = {
  proxies: names.map((name) => ({ name, type: 'ss', server: '127.0.0.1', port: 1, uuid: 'u' })),
  rules: [],
  'proxy-groups': [],
  'proxy-providers': {},
}
const main = new Function('args', 'return (function(){' + src + '\\nreturn main})()')({})
const out = main(config)
const groups = (out['proxy-groups'] || []).map((g) => ({
  name: g.name,
  type: g.type,
  proxyCount: Array.isArray(g.proxies) ? g.proxies.length : 0,
}))
console.log(JSON.stringify({ groups, rules: out.rules }))
"""


@pytest.fixture(scope="module")
def artifact_summary() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 不可用，跳过产物冒烟")
    if not ARTIFACT.exists():
        pytest.skip(f"缺少产物文件: {ARTIFACT}")
    proc = subprocess.run(
        [node, "-e", HARNESS],
        capture_output=True,
        text=True,
        env={"ARTIFACT_PATH": str(ARTIFACT), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_artifact_runs_and_keeps_custom_rules_first(artifact_summary: dict):
    rules = mo.load_rules(ROOT / "custom_rules.yaml")
    head = artifact_summary["rules"][: len(rules)]
    tail = artifact_summary["rules"][len(rules) :]
    assert head == rules
    assert tail[-1].startswith("MATCH,")


def test_artifact_groups_are_unique_and_capped(artifact_summary: dict):
    groups = artifact_summary["groups"]
    names = [g["name"] for g in groups]
    assert len(names) == len(set(names))

    auto_name = re.search(
        r"name: '([^']+)',\n    type: 'url-test',\n    tolerance: 50",
        mo.FUNCTIONAL_GROUPS_NEW,
    ).group(1)
    auto = [g for g in groups if g["name"] == auto_name]
    assert len(auto) == 1
    assert auto[0]["proxyCount"] <= mo.DEFAULT_AUTO_SELECT_MAX

    failover_subs = [name for name in names if name.startswith(mo.FAILOVER_PREFIX)]
    assert len(failover_subs) >= 2
    assert len([g for g in groups if g["type"] == "fallback"]) == len(failover_subs)
