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
    "rules.unshift(\"DOMAIN-SUFFIX,15.204.105.50:25461,SG新加坡\");",
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

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined_code)

    print(f"合并完成，已保存到: {output_path}")

except Exception as e:
    print("合并出错:", e)
    exit(1)
