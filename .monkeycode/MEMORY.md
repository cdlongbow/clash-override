# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[任何写入后必须回读并扫描异常字符]
- Date: 2026-10-31
- Context: 用户在代码审查后的 P0 改动交付时提出；此前 Agent 用 Edit/Python 脚本写文件时出现过字面量被截断损坏（如 DOMAIN-SUFFIX,a.com 被写成残缺串）
- Instructions:
  - 任何写文件操作（Write / Edit / 脚本落盘）完成后必须立刻回读被改动的文件确认内容，禁止写完即认为成功
  - 回读时同步做异常字符扫描：U+FFFD、零宽字符（U+200B/200C/200D）、BOM、NBSP、U+2028/2029、C0/C1 控制字符（制表符除外）、代理项与未分配码点
  - 回读时核对关键内容完整性：关键标识符/字面量出现次数、文件结构（Python 可编译、测试函数数量、Markdown 代码围栏配对、中文括号配对）
  - 发现损坏立即修好并重新回读，修完再复跑构建或测试再交付


[用户是编程小白，回复用中文大白话 + 北京时间]
- Date: 2026-10-31（北京时间 12:29，Asia/Shanghai）
- Context: 用户自我介绍是小白，并规定了表达语言、时区与讲解方式
- Instructions:
  - 全程用简体中文回复，包含思考过程与工具调用的标题说明
  - 日期时间一律按北京时间（UTC+8）表述，需要时先换算再写
  - 用大白话讲，减少术语；确实用到术语时随手补一句解释
  - 尽量举例子或给对照场景，例如用「订阅里 直连|双线 这类条目」讲清剔除规则的效果
  - 先给结论和怎么操作，再按需补原理，讲明白就收

[.monkeycode/MEMORY.md 需要入库复用]
- Date: 2026-10-31
- Context: 用户要求把记忆文件提交进仓库，方便后续会话和其他 Agent 复用
- Instructions:
  - `.monkeycode/MEMORY.md` 纳入 git 跟踪，内容有新增或修订时随当次改动一起提交
  - 提交只带 MEMORY.md，`.monkeycode-tmp-files/` 这类临时目录保持忽略
