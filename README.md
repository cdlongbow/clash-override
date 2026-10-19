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
```

### 2. 生成覆盖脚本

```bash
pip install -r requirements.txt
python merge_override.py
```

运行后会在当前目录生成 `my_merged_override.js`。

常用参数：

```bash
python merge_override.py --rules custom_rules.yaml --output my_merged_override.js
python merge_override.py --offline
```

`--offline` 使用上次下载的 `.yanet_cache.js`，不访问网络。

### 3. 导入 Clash 客户端

将生成的 `my_merged_override.js` 导入 Clash Verge Rev 或 Mihomo Party 的覆盖脚本配置中。也可以直接使用 jsDelivr 链接导入：

```
https://fastly.jsdelivr.net/gh/cdlongbow/clash-override@main/my_merged_override.js
```

## 工作原理

1. 依次尝试多个 CDN / GitHub 源拉取最新 YaNet 优化脚本，全部失败时回退本地缓存
2. 读取 `custom_rules.yaml`，在 `if (!enable) return config` 后一次性 `rules.unshift(...)` 注入
3. 自定义规则优先级最高
4. 自动注入「自动选择」和「故障转移」全局策略组
5. 任一锚点替换失败会直接报错，避免生成半残脚本

## 生成策略组

脚本会额外注入以下全局策略组，位于「默认节点」列表最前面：

| 策略组 | 类型 | 说明 |
|--------|------|------|
| 自动选择 | url-test | 从已分类的可用节点中自动选延迟最低的，已排除高倍率和中国节点 |
| 故障转移 | select | 手动选一个地区，内部 fallback 只在同地区节点间切换，挂了才切下一个 |

故障转移会为每个有 ≥2 个节点的地区生成子组（如 故障转移-JP日本、故障转移-US美国），确保不跨地区跳。子组写入独立数组后再合并，避免遍历时重复生成。

## 文件说明

| 文件 | 说明 |
|------|------|
| `custom_rules.yaml` | 自定义分流规则（日常只改这个） |
| `merge_override.py` | 构建脚本，拉取远程脚本并注入自定义规则 |
| `my_merged_override.js` | 合并后的覆盖脚本（产物），可在 Clash 中直接使用 |
| `requirements.txt` | Python 依赖 |
| `tests/` | 合并逻辑单测 |

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
