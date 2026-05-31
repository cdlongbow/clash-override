import requests
import re

# ============ 你的自定义规则 ============
# 这些规则会插入到远程脚本 main 函数的最前面
custom_rules = [
    "config.rules.unshift(\"DOMAIN-SUFFIX,libredmm.com,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,api.tmdb.org,DIRECT\");",
    "config.rules.unshift(\"DOMAIN,api.thejavdb.net,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,epg.pw,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,dmmsee.cyou,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,c97k.com,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,javdb573.com,DIRECT\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,javdb.com,US美国\");",
    "config.rules.unshift(\"DOMAIN-KEYWORD,dmm,JP日本\");",
    "config.rules.unshift(\"DOMAIN-KEYWORD,mgstage,JP日本\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,amazon.co.jp,JP日本\");",
    "config.rules.unshift(\"DOMAIN-SUFFIX,seesaa.jp,JP日本\");",
]

# ============ 远程脚本地址 ============
remote_url = "https://fastly.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js"

# ============ 输出文件名 ============
output_path = "my_merged_override.js"

try:
    print("正在下载远程脚本...")
    resp = requests.get(remote_url, timeout=15)
    resp.raise_for_status()
    remote_code = resp.text
    print(f"下载成功，脚本长度: {len(remote_code)}")

    # 找到 function main(config) { 的位置，并在其后插入自定义规则
    # 使用正则匹配到函数体开始的大括号
    pattern = r'(function\s+main\s*\(config\s*\)\s*\{)'
    match = re.search(pattern, remote_code)
    if not match:
        raise ValueError("未找到 function main(config) { 声明，远程脚本格式可能已变化")

    insert_pos = match.end()  # 大括号之后的位置
    # 构造插入代码：换行 + 自定义规则 + 换行 + 注释
    insert_code = "\n  // === 以下为用户自定义优先规则 ===\n"
    for rule in custom_rules:
        insert_code += f"  {rule}\n"
    insert_code += "  // === 自定义规则结束 ===\n"

    # 组合最终代码
    combined_code = (
        remote_code[:insert_pos] +
        insert_code +
        remote_code[insert_pos:]
    )

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined_code)

    print(f"合并完成，已保存到: {output_path}")

except Exception as e:
    print("合并出错:", e)
    exit(1)