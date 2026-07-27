import requests
import re

# ============ 你的自定义规则 ============
custom_rules = [
    "rules.unshift(\"DOMAIN-SUFFIX,libredmm.com,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,api.tmdb.org,DIRECT\");",
    "rules.unshift(\"DOMAIN,api.thejavdb.net,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,epg.pw,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,dmmsee.cyou,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,c97k.com,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,javdb573.com,DIRECT\");",
    "rules.unshift(\"DOMAIN-SUFFIX,javdb.com,US美国\");",
    "rules.unshift(\"IP-CIDR,15.204.105.50/32,自动选择,no-resolve\");",
    "rules.unshift(\"DOMAIN-KEYWORD,dmm,JP日本\");",
    "rules.unshift(\"DOMAIN-KEYWORD,mgstage,JP日本\");",
    "rules.unshift(\"DOMAIN-SUFFIX,amazon.co.jp,JP日本\");",
    "rules.unshift(\"DOMAIN-SUFFIX,seesaa.jp,JP日本\");",
]

remote_url = "https://fastly.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js"
output_path = "my_merged_override.js"

try:
    print("正在下载远程脚本...")
    resp = requests.get(remote_url, timeout=15)
    resp.raise_for_status()
    remote_code = resp.text
    print(f"下载成功，脚本长度: {len(remote_code)}")

    # 定位 if (!enable) return config 这一行（允许末尾有分号或换行）
    pattern = r'(if\s*\(!enable\)\s*return\s+config\s*;?\s*\n)'
    match = re.search(pattern, remote_code)
    if not match:
        raise ValueError("未找到 'if (!enable) return config' 语句，脚本格式可能已变")

    insert_after = match.end()
    # 构建插入代码
    insert_code = "\n  // === 以下为用户自定义优先规则 ===\n"
    for rule in custom_rules:
        insert_code += f"  {rule}\n"
    insert_code += "  // === 自定义规则结束 ===\n"

    combined_code = (
        remote_code[:insert_after] +
        insert_code +
        remote_code[insert_after:]
    )

    # 插入 allProxyNames 声明（在 generatedRegionGroups 之前）
    combined_code = combined_code.replace(
        "  const generatedRegionGroups = []",
        "  const allProxyNames = proxies.map((p) => p.name).filter(n => "
        "n !== '直连' && n !== '拒绝' && "
        "!n.includes('中国') && !n.includes('CN') && !n.includes('China') && !n.includes('未知')"
        ")\n\n  const generatedRegionGroups = []",
    )

    # 替换 functionalGroups 初始化块，注入自动选择 + 故障转移子组
    global_groups = (
        "  const functionalGroups = []\n\n"
        "  // 全局自动选择（url-test）\n"
        "  functionalGroups.push({\n"
        "    ...groupBaseOption,\n"
        "    name: '自动选择',\n"
        "    type: 'url-test',\n"
        "    tolerance: 50,\n"
        "    proxies: allProxyNames,\n"
        "    icon: 'https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Available.png',\n"
        "  })\n\n"
        "  // 为每个地区生成故障转移子组（同名地区内 fallback）\n"
        "  const fallbackGroupNames = []\n"
        "  generatedRegionGroups.forEach(g => {\n"
        "    if (g.proxies.length > 1) {\n"
        "      const fbName = '故障转移-' + g.name\n"
        "      fallbackGroupNames.push(fbName)\n"
        "      generatedRegionGroups.push({\n"
        "        ...groupBaseOption,\n"
        "        name: fbName,\n"
        "        type: 'fallback',\n"
        "        url: 'https://www.gstatic.com/generate_204',\n"
        "        proxies: g.proxies,\n"
        "        icon: g.icon,\n"
        "      })\n"
        "    }\n"
        "  })\n\n"
        "  if (fallbackGroupNames.length > 0) {\n"
        "    functionalGroups.push({\n"
        "      ...groupBaseOption,\n"
        "      name: '故障转移',\n"
        "      type: 'select',\n"
        "      proxies: fallbackGroupNames,\n"
        "      icon: 'https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Global.png',\n"
        "    })\n"
        "  }\n"
    )
    combined_code = combined_code.replace(
        "  const functionalGroups = []",
        global_groups,
    )

    # 更新"默认节点"的 proxies 列表，加入新策略组
    combined_code = combined_code.replace(
        "proxies: [...regionGroupNames, '其他节点', '直连']",
        "proxies: ['自动选择', ...(fallbackGroupNames.length > 0 ? ['故障转移'] : []), ...regionGroupNames, '其他节点', '直连']",
    )

    # 所有服务策略组也加入自动选择和故障转移
    combined_code = combined_code.replace(
        "groupProxies = ['默认节点', ...regionGroupNames, '直连']",
        "groupProxies = ['自动选择', '故障转移', '默认节点', ...regionGroupNames, '直连']",
    )
    combined_code = combined_code.replace(
        "groupProxies = ['默认节点', '直连', ...regionGroupNames]",
        "groupProxies = ['自动选择', '故障转移', '默认节点', '直连', ...regionGroupNames]",
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined_code)

    print(f"合并完成，已保存到: {output_path}")

except Exception as e:
    print("合并出错:", e)
    exit(1)
