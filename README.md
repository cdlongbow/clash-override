# clash-override

为 Clash Verge Rev / Mihomo Party 生成覆盖脚本，基于 [YaNet](https://github.com/dahaha-365/YaNet) 优化脚本自动注入自定义分流规则。

## 使用方式

### 1. 编辑自定义规则

修改 `custom_rules.yaml`，按 Clash 规则语法添加分流。越靠前优先级越高。

```yaml
rules:
  - DOMAIN-SUFFIX,example.com,DIRECT
  - DOMAIN-SUFFIX,api.example.org,US美国
  - DOMAIN-KEYWORD,dmm,JP日本
  - IP-CIDR,15.204.105.50/32,自动选择,no-resolve

# 目标策略指向订阅里的节点名时，在这里登记，供构建期校验放行
allowed_policies:
  - My-Node-01

# 可选：自动选择组的节点数上限（0 表示不限），默认 80
auto_select_max: 80

# 可选：锁定上游脚本 sha256，全部源都不匹配时报错，防上游被替换后无感生效
expected_sha256:
  - 96dd4374113a4df2d4e90ad1de5b17964581de1d6c41177faee8b13da6fc8215

# 可选：「其他节点」组类型，url-test 自动测速（默认），select 保留手动选
other_group_type: url-test

# 可选：从自建组里剔除的代理类型与名字前缀（默认值见下）
drop_proxy_types: [direct, reject, reject-drop, pass, compatible]
drop_name_tokens: [直连, 拒绝, 放行, 屏蔽, 拦截, direct, reject, pass, compatible]
```

订阅里常见的入口类条目会被自动剔除，不再混进「其他节点」「自动选择」：`type` 属于 `drop_proxy_types` 的条目（direct / reject 等），以及名字第一个片段命中 `drop_name_tokens` 的条目（例如 `直连|双线` 的首段 `直连`）。片段按 `|`、`/`、`-`、`_`、`.`、`,`、`:`、空格切分，命中规则是整段相等，因此 `HK Direct 专线` 这类真节点会被保留。想再剔除公益订阅里的广告条目，把它的名字首段加进 `drop_name_tokens` 即可。

规则类型有白名单校验：`DOMAIN` / `DOMAIN-SUFFIX` / `DOMAIN-KEYWORD` / `DOMAIN-REGEX` / `GEOSITE` / `GEOIP` / `IP-CIDR` / `IP-CIDR6` / `SRC-IP-CIDR` / `IP-SUFFIX` / `DST-PORT` / `SRC-PORT` / `PROCESS` / `PROCESS-NAME` / `RULE-SET` / `NETWORK` / `IN-TYPE` / `UID` / `SUB-RULE` / `MATCH` / `FINAL`。`MATCH`、`FINAL` 写成 `MATCH,策略组` 两段式，其余类型必须是 `类型,匹配内容,策略[,no-resolve]`。

### 2. 生成覆盖脚本

```bash
pip install -r requirements.txt
python merge_override.py
```

运行后会生成 `my_merged_override.js`（默认落在脚本所在目录；`--rules`/`--output`/`--cache` 传相对路径时按当前工作目录解析）。

常用参数：

```bash
python merge_override.py --rules custom_rules.yaml --output my_merged_override.js
python merge_override.py --offline
python merge_override.py --allow-policy My-Node-01 --allow-policy My-Node-02
python merge_override.py --skip-policy-check
python merge_override.py --auto-select-max 40
python merge_override.py --expect-sha256 96dd4374113a4df2d4e90ad1de5b17964581de1d6c41177faee8b13da6fc8215
python merge_override.py --other-group-type select
python merge_override.py --print-hash
python inspect_groups.py
```

- `--offline`：使用上次下载的 `.yanet_cache.js`，不访问网络
- `--allow-policy`：临时放行额外的目标策略名（等价于 YAML 里的 `allowed_policies`），可重复
- `--skip-policy-check`：跳过策略名校验（策略名唯一性 + 规则目标存在性）
- `--auto-select-max`：覆盖 YAML 的 `auto_select_max`，CLI 优先
- `--expect-sha256`：追加期望的上游 sha256，可重复，与 YAML 里的列表合并
- `--other-group-type`：覆盖 YAML 的 `other_group_type`（`url-test` / `select`）
- `--print-hash`：只打印上游脚本的 sha256，不生成也不改动任何文件（配合锁定使用）

构建期校验清单：

1. YAML 合法性、规则类型白名单与字段完整性
2. 每条规则的目标策略在生成脚本里真实存在（策略名从产物静态提取，含派生的 `故障转移-<地区>`）
3. 产物里策略名全局唯一（重名会让 Clash 拒载）
4. 上游来源可信：打印 sha256，可用 `expected_sha256` 锁定；缓存回退时提示缓存年龄
5. CI 侧再跑 `node --check` 与产物冒烟（合成节点跑一遍 `main()`）

「自动选择」组按地区轮转取样，最多 `auto_select_max` 个节点，避免节点多的订阅把 url-test 探测拉爆；要全量节点就设 0。

### 上游脚本锁定与刷新

`custom_rules.yaml` 里的 `expected_sha256` 会把上游脚本钉在某个版本：上游内容一变，构建直接失败并提示刷新流程，避免别人替换脚本后你无感地跑上。

上游正常升级后，按下面三步刷新：

```bash
# 看一眼新版本算出来的 sha256，这一步不写任何文件
python merge_override.py --print-hash

# 把打印出的值粘进 custom_rules.yaml 的 expected_sha256 列表
# 然后离线重建一次，确认能通过
python merge_override.py --offline
```

`--print-hash` 会忽略现有的锁定值，所以旧值就算已经失配也能拿到新值。

### 体检已生成的脚本

```bash
python inspect_groups.py
python inspect_groups.py --json
```

只读脚本，不写任何文件。它用假节点在 node 里真跑一遍 `main()`，把策略组列成表（组名、类型、成员数），并检查空组、组名重名、残留入口类条目、测速组超上限这几类会让 Clash 拒载或体验变差的问题。退出码 0 表示没问题，1 表示发现问题，2 表示环境缺 node。

### 3. 导入 Clash 客户端

将生成的 `my_merged_override.js` 导入 Clash Verge Rev 或 Mihomo Party 的覆盖脚本配置中。也可以直接使用 jsDelivr 链接导入：

```
https://fastly.jsdelivr.net/gh/cdlongbow/clash-override@main/my_merged_override.js
```

想固定版本、不想被上游自动构建影响，把 `@main` 换成发布标签，例如 `@v1.0`；回滚时换回旧标签即可。

## 工作原理

1. 依次尝试多个 CDN / GitHub 源拉取最新 YaNet 优化脚本，全部失败时回退本地缓存
2. 读取 `custom_rules.yaml`，先做规则语法校验（类型白名单、字段完整性、YAML 合法性）
3. 在 `if (!enable) return config` 后一次性 `rules.unshift(...)` 注入，自定义规则优先级最高
4. 剔除 direct/reject 类与 `直连|xxx` 形式的入口条目，再注入「自动选择」「故障转移」全局策略组；「其他节点」默认改为 url-test
5. 用产物里静态出现的策略组名校验所有自定义规则的目标策略，缺失即报错
6. 校验产物策略名唯一，重名会让 Clash 整体拒载
7. 任一锚点替换失败会直接报错，避免生成半残脚本

策略组存在性校验基于静态文本提取（脚本里出现的 `name: '...'` 字面量，外加内建的 `DIRECT` / `REJECT` / `PASS` / `GLOBAL`，以及派生的 `故障转移-<地区>` 名）。上游若改成运行时拼接的组名，可能出现误报，这类情况用 `allowed_policies` 放行即可。

## 生成策略组

脚本会额外注入以下全局策略组，位于「默认节点」列表最前面：

| 策略组 | 类型 | 说明 |
|--------|------|------|
| 自动选择 | url-test | 从可用节点里自动选延迟最低的，已排除高倍率与中国节点；节点数按地区轮转取样，上限由 `auto_select_max` 控制 |
| 故障转移 | select | 手动选一个地区，内部 fallback 只在同地区节点间切换，挂了才切下一个 |

「其他节点」收的是没命中任何地区正则的剩余节点，成员同样经过剔除；类型默认 url-test（`other_group_type` 可设回 select）。

故障转移会为每个有 ≥2 个成员的分组生成子组（如 故障转移-JP日本、故障转移-US美国、故障转移-其他节点），确保不跨地区跳。子组写入独立数组后再合并，避免遍历时重复生成。

## 文件说明

| 文件 | 说明 |
|------|------|
| `custom_rules.yaml` | 自定义分流规则（日常只改这个） |
| `merge_override.py` | 构建脚本，拉取远程脚本并注入自定义规则 |
| `inspect_groups.py` | 只读体检脚本，列出策略组并检查常见问题 |
| `my_merged_override.js` | 合并后的覆盖脚本（产物），可在 Clash 中直接使用 |
| `requirements.txt` | Python 依赖 |
| `tests/` | 合并逻辑单测 + 产物冒烟测试（需要 node，缺失时自动跳过） |
| `THIRD_PARTY_NOTICE.md` | 上游 YaNet 脚本的 BSD 3-Clause 许可与署名 |

## 自定义规则示例

```yaml
rules:
  - DOMAIN-SUFFIX,libredmm.com,DIRECT
  - DOMAIN-SUFFIX,javdb.com,US美国
  - DOMAIN-KEYWORD,dmm,JP日本
  - IP-CIDR,15.204.105.50/32,默认节点,no-resolve
```

规则格式与 Clash 规则语法一致。可用地区策略组包括：HK香港、US美国、JP日本、KR韩国、SG新加坡、TW台湾省、GB英国、DE德国 等。

## 测试

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

`tests/test_artifact_smoke.py` 会用 node 加载已提交的 `my_merged_override.js`，喂合成节点跑一遍 `main()`，校验自定义规则排在最前、策略名唯一、自动选择节点数不越界；本机或 Runner 没有 node 时该用例自动跳过。

本地手动冒烟：

```bash
python merge_override.py --offline
node --check my_merged_override.js
```

## 许可

构建产物是上游 [YaNet](https://github.com/dahaha-365/YaNet) 的修改衍生作品，上游为 BSD 3-Clause（Copyright (c) 2024, Dahaha）。版权声明与免责条款见 `THIRD_PARTY_NOTICE.md`，生成脚本文件头保留原作者署名与仓库地址。
