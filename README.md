# clash-override

为 Clash Verge Rev / Mihomo Party 生成覆盖脚本，基于 [YaNet](https://github.com/dahaha-365/YaNet) 优化脚本自动注入自定义分流规则。

## 使用方式

### 1. 编辑自定义规则

修改 `merge_override.py` 中的 `custom_rules` 列表，按需添加你的分流规则：

```python
custom_rules = [
    "rules.unshift(\"DOMAIN-SUFFIX,example.com,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,api.example.org,US美国\");",
]
```

### 2. 生成覆盖脚本

```bash
pip install requests
python merge_override.py
```

运行后会在当前目录生成 `my_merged_override.js`。

### 3. 导入 Clash 客户端

将生成的 `my_merged_override.js` 导入 Clash Verge Rev 或 Mihomo Party 的覆盖脚本配置中。也可以直接使用 jsDelivr 链接导入：

```
https://fastly.jsdelivr.net/gh/cdlongbow/clash-override@main/my_merged_override.js
```

## 工作原理

1. 从远程拉取最新 YaNet 优化脚本
2. 在 `if (!enable) return config` 语句后注入 `custom_rules` 中的自定义规则
3. 自定义规则通过 `rules.unshift()` 确保优先级最高
4. 自动注入两个全局策略组

## 生成策略组

脚本会额外注入以下全局策略组，位于「默认节点」列表最前面：

| 策略组 | 类型 | 说明 |
|--------|------|------|
| 自动选择 | url-test | 从所有节点中自动选延迟最低的 |
| 故障转移 | select | 手动选一个地区，内部 fallback 只在同地区节点间切换，挂了才切下一个 |

故障转移会为每个有 ≥2 个节点的地区自动生成子组（如 故障转移-JP日本、故障转移-US美国），确保不跨地区跳避免被风控。

## 文件说明

| 文件 | 说明 |
|------|------|
| `merge_override.py` | 构建脚本，拉取远程脚本并注入自定义规则 |
| `my_merged_override.js` | 合并后的覆盖脚本（产物），可在 Clash 中直接使用 |
| `requirements.txt` | Python 依赖 |

## 自定义规则示例

```python
# 直连
"rules.unshift(\"DOMAIN-SUFFIX,libredmm.com,DIRECT\");",

# 指定地区节点
"rules.unshift(\"DOMAIN-SUFFIX,javdb.com,US美国\");",
"rules.unshift(\"DOMAIN-KEYWORD,dmm,JP日本\");",

# 指定节点 + no-resolve
"rules.unshift(\"IP-CIDR,15.204.105.50/32,默认节点,no-resolve\");",
```

规则格式与 Clash 规则语法一致，默认可用的地区策略组包括：HK香港、US美国、JP日本、KR韩国、SG新加坡、TW台湾省、GB英国、DE德国 等。
