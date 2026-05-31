import requests
import os

# ============ 你的自定义规则 ============
custom_rules_code = """
function main(config) {
  // 先把你要直连的网站插到规则最前面
  config.rules.unshift("DOMAIN-SUFFIX,libredmm.com,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,api.tmdb.org,DIRECT");
  config.rules.unshift("DOMAIN,api.thejavdb.net,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,epg.pw,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,dmmsee.cyou,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,c97k.com,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,javdb573.com,DIRECT");
  config.rules.unshift("DOMAIN-SUFFIX,javdb.com,US美国");
  config.rules.unshift("DOMAIN-KEYWORD,dmm,JP日本");
  config.rules.unshift("DOMAIN-KEYWORD,mgstage,JP日本");
  config.rules.unshift("DOMAIN-SUFFIX,amazon.co.jp,JP日本");
  config.rules.unshift("DOMAIN-SUFFIX,seesaa.jp,JP日本");
  return config;
}
"""

remote_url = "https://fastly.jsdelivr.net/gh/dahaha-365/YaNet@main/Mihomo/global_script.js"
output_path = "my_merged_override.js"   # 输出到当前目录

try:
    print("正在下载远程脚本...")
    resp = requests.get(remote_url, timeout=15)
    resp.raise_for_status()
    remote_code = resp.text
    print("下载成功，长度:", len(remote_code))

    # 去掉远程脚本里可能存在的 function main 外壳
    start = remote_code.find("{")
    end = remote_code.rfind("}")
    if start != -1 and end != -1:
        remote_body = remote_code[start+1:end]
    else:
        remote_body = remote_code

    # 拼接：你的规则 + 远程脚本逻辑
    combined_code = custom_rules_code.rstrip().rstrip("}")
    combined_code += "\n  // === 以下来自远程脚本 ===\n"
    combined_code += remote_body + "\n"
    combined_code += "  return config;\n}"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(combined_code)

    print(f"合并完成，文件已保存: {os.path.abspath(output_path)}")
except Exception as e:
    print("出错了:", e)
    exit(1)