## v1.4.11 — 2026-10-14

**独立审计加固——修复 39 处缺陷（DSH round 1：40 项发现，12 高 / 15 中 / 13 低）。**
工具包首次接受完整独立代码审计（DeepSeek Harness，逐模块通读，每项发现先本地
复现再修复）。审计暴露的核心模式：工具失败时「自信地沉默」而不是大声报错。
本版修复全部 39 项已验证发现；1 项（Brave `count` 字段 schema）标记 UNVERIFIED，
等一次带 key 的真实响应确认。

高危修复：
- `mcp`：competitor_gap 在 MCP 上完全不可用——每次调用都附加不支持的
  `--json` 直接报错（注册表补 `json_flag: False`）。
- `keyword_research` / `geo_fanout` / `reddit_blueocean`：autocomplete
  响应 `["q", null]` 返回 `None` 导致所有调用方崩溃；现返回 `[]`。
- `site_audit`：JSON-LD `@type` 匹配用了字面 `\s*`，格式化排版的结构化
  数据全部检测不到（Product/FAQ 永远 missing）；首页永远被报成孤儿页
  （链接映射丢掉了 `/`）。
- `ai_crawler_audit`：连续 `User-agent:` 行互相覆盖——`Disallow: /` 组
  对除最后一个 agent 外全部读成「未列出」。
- `rank_tracker`：`lstrip("www.")` 会啃域名（`walmart.com` → `almart.com`
  永远匹配不上）；子串匹配会把别人的排名存成你的；999 未找到哨兵值
  捏造 ±996 位的「趋势」。
- `search_intent`：裸 `get` 词元把「how to get more traffic」判成
  transactional。`serp_intent`：未锚定的路径规则把 `/blog/product-led-growth`
  归类为 product；百分比硬除以 10。
- `competitor_gap`：子 sitemap 静默截断前 10 个（残缺清单当完整对比）；
  `--compare` 按 netloc 做 key，同域多份 sitemap 互相覆盖。
- `geo_fanout`：反向包含判断把所有子查询标成「有真实搜索需求」；
  维度报告同一个标题最多打 3 遍。
- `kgr_auto`：缺 Bing key 时先承诺优雅降级然后整个进程退出
  （keyword_volume 库调用现返回零值，CLI 仍然明确报错退出）。
- `reddit_blueocean`：子串匹配让 `top` 命中 *laptop*/*desktop*。

中低危：MCP 协议协商诚实化（不支持的版本回落而非回声）、参数错误映射
-32602；`content_qc` 统计 CJK 字符（中文稿的发布门禁原来是空转）；
`search_performance` 分页拉取 GSC 行（top-50 小计不再冒充总量）；
`keyword_cluster` 正确解析带引号 CSV；`content_matrix` JSON 输入做数值
转换；`domain_rating` 缓存在 site-packages 不可写时回落 ~/.zens_ink；
`llms_gen` 解码 sitemap 实体、404 sitemap 不再裸崩；`setup_gsc` 裸文件名
路径不再丢掉刚授权的 OAuth token；CLI 派发器补上 `content_qc` +
`llms_gen`（此前有文档但报 Unknown tool）；TOOLS_COUNT 20 → 22；
SKILL.md frontmatter 刷新（此前停在 v1.2.1 / 13 工具）。

第二轮（全量复核）：37/39 完全修复，2 项 PARTIAL（geo_fanout 前缀
过验证；kd HTTP 错误处理），1 项正确 DEFERRED——另发现修复本身引入
2 个新缺陷（serp_intent 的 /guide 类模式未锚定，把 /pricing/guide 误判
为 blog；content_matrix JSON 只转换 3/6 个数值字段）。第三轮四项全部
修正：内容路径模式完全锚定（/pricing/guide 归 pricing、/guide/x 归
blog）、双分支六字段数值转换、live demand 精确匹配、kd HTTPError 处理。
第二轮报告归档 `docs/audit-2026-10-14-dsh-round2.md`。

第三轮（四项抽查）：全部确认 FIXED，v1.4.11 获准发版。报告归档
`docs/audit-2026-10-14-dsh-round{1,2,3}.md`。

新增 `tests/test_audit_fixes.py`——18 条回归测试钉死以上修复；冒烟测试
同步扩展。审计报告归档于仓库内 `docs/audit-2026-10-14-dsh-round1.md`、
`docs/audit-2026-10-14-dsh-round2.md`。

## v1.4.10 — 2026-10-01

**品牌卡片更新。**
- 新 hero banner（中英双语）：现行 Z 标 + 工具管线 + `pip install`
  命令行——替换退役的墨水滴旧设计。
- README 头图改为绝对 URL，PyPI 页面也能正常显示。

## v1.4.9 — 2026-09-30

**仓库 agent 层——让仓库本身对 AI 可读。**
Gitingest、GitDiagram（合计 15k+ stars）把「AI 工具如何消化你的仓库」变成了
真实入口：agent 先通过这些摘要认识项目，再见到代码。本版为 zens-ink 自身
补上这一层，并用新的 Pro repo_readiness 审计自测。

- **llms.txt + llms-full.txt**（仓库根目录）——agent 可读摘要：
  20 个工具清单、MCP / skill 入口、安装命令、链接。
- **ARCHITECTURE.md**——一页讲清模块分层与数据流。
- **冒烟测试**（`tests/test_smoke.py`）——import 与 CLI 面回归保障。
- **FUNDING.yml**——指向 zens.ink 定价页。
- 经 Pro v2.6.0 `repo_readiness` 审计验证：76/C → 91/A。
  对照：gitdiagram 63/D、psf/requests 59/F。

## v1.4.8 — 2026-09-08

**新工具：ai_crawler_audit — 查清谁真的能读你的内容。**
site_audit 查页面，这个查守门人。对 robots.txt 里的 17 个 AI 爬虫
（训练类 vs AI 搜索类，按厂商分组）逐个判定可达性，读取 Content Signals
内容信号，验证 llms.txt / llms-full.txt 发现层，输出百分制 AI 可读性
评分和人话建议。全站封禁与子路径封禁严格区分——`Disallow: /admin` 不等于
`Disallow: /`。零依赖、免 API key。与 llms_gen 配对使用：先审计现有策略，
缺什么生成什么。

- **新工具 ai_crawler_audit**：robots.txt AI 爬虫策略 + llms.txt 发现层审计，
  带 AI 可读性评分，支持 Markdown / JSON 输出
- 已在真实站点上验证全谱系策略：全放行、子路径封禁、全站封禁、内容信号策略
- 版本号 1.4.7 → 1.4.8，工具数 19 → 20

# 更新日志

## v1.4.7 — 2026-08-29

**两个新工具：content_qc + llms_gen —— 发布侧 GEO 闭环补齐。**
给线上页面打分（site_audit、geo score）是事后诊断。这两个工具把检查挪到发布前，
并自动生成 AI 发现层。

- **新工具 content_qc** —— AI 可引用内容的发布前门禁。14 项加权检查：BLUF 前置、
  事实密度（每千词）、模糊词上限、外链来源、FAQ 块、问题式标题、标题/描述长度、
  alt 覆盖、日期信号。支持 Markdown + HTML、目录批量、`--min-score` 门禁 + CI 退出码。
  已在真实站点上与 site_audit 交叉验证。
- **新工具 llms_gen** —— 从静态构建目录或远程 sitemap 生成 `llms.txt`（精简版）+
  `llms-full.txt`（全量目录，按 section 分组）。自动跳过 admin/api/noindex 路由。零依赖。
- 版本 1.4.6 → 1.4.7。

## v1.4.6 — 2026-08-23

**PyPI 发布基建。** zens-ink 进入 pip 时代，后续发版由 git tag 自动完成。

- 上架 PyPI：`pip install zens-ink`（替代 git+https 安装命令）
- GitHub Actions 自动发版：push `v*` tag 触发 CI 构建 + twine 上传（PYPI_API_TOKEN 为仓库 secret）
- TOOLS_COUNT 修正：16 -> 19（工具注册计数落后于实际工具集）

## v1.4.5 — 2026-08-23

**新工具：domain_rating —— 免费 Ahrefs 真实 DR。** Off-page 权重一直是已知空白：kd.py 此前只能用人工整理的权威域名表做代理。Ahrefs 开放了免费公共 Domain Rating 端点，这个空白零成本补上：

- `domain_rating` 查询 `v3/public/domain-rating-free`，任意域名或 URL 返回 0-100 DR
- 支持命令行传参、`--file` 文件、stdin 管道三种输入——专为批量查 SERP 竞品设计
- 本地缓存（`dr-cache.json`，已 gitignore），重复查询不打接口；`--no-cache` 可跳过
- CSV / JSON 导出；URL 自动归一化（`https://www.example.com/x` → `example.com`）
- 已同步注册进 MCP server 工具列表
- 按 DR License 要求，所有输出附带 "Domain Rating by Ahrefs" 署名
- 需要免费 AHREFS_API_KEY（app.ahrefs.com/account/api-keys 生成）

## v1.4.4 — 2026-08-23

**site_audit 新增 agent-readiness 检查。** 网站越来越多地被自主 agent 阅读，而不只是人和爬虫。`site_audit` 现在会标记 llms.txt 里决定 agent 能否理解你产品的两个缺口：

- **新检查：agent when-to-use** —— llms.txt 没有 `When to use` 段落时只是营销文案而非指引，agent 判断不出你的站适合什么任务。警告级别，附修复提示。
- **新检查：agent how-to-call** —— llms.txt 没有安装命令 / 端点 / MCP 入口时，agent 发现了你也没法调用。信息级别。
- 两项检查均为确定性规则、零依赖，跑在现有 `site_audit` 流程里，不需要新参数。
- 已用生产构建验证：完整 llms.txt 干净通过；删掉 when-to-use 段落后正确触发警告。

背景：本次与 ZensInk Pro v2.4.0 同步发布——Pro 新增完整 Agent Readiness 评分（8 项检查、0-100 分、P0/P1/P2 修复方案）。该清单的参考实现让 zens.ink 在 [is-agentic.com](https://is-agentic.com/scan/zens.ink) 从 64 分升到 98 分。

## v1.4.3 — 2026-08-15

**kd 品牌词指纹 + 排名追踪。**

- kd 品牌三重指纹：官方域名进 top3、域名家族占位 ≥2、平台生态密度——品牌词不再污染通用 KD
- `kd_entry`：剔除官方页与平台固定位后的截流难度
- KD → 引用域外链预算曲线（编辑型/目录型双轨）
- `--markdown` 自包含报告模式
- **新工具：rank_tracker** —— 基于 SQLite 的关键词排名历史
- competitor_gap：更深的 sitemap 解析

## v1.4.2 — 2026-08-14

- **MCP stdio server** —— `zens-ink mcp` 把所有 CLI 工具作为原生模型工具暴露给 MCP 客户端（DSH、Claude、Codex）
- **新工具：serp_intent** —— Serper 驱动的 SERP 意图评估（20+ 页面类型、4 种意图、SERP 特征检测）；与关键词版 `search_intent` 交叉验证

## v1.4.1 — 2026-08-06

- **新工具：geo_fanout** —— Query Fan-out 内容规划
- **新工具：reddit_blueocean** —— Google Autocomplete 挖 Reddit 蓝海
- site_audit：+3 项检查（staging 泄漏检测、sitemap 清单、schema 字段校验）

## v1.3.0 — 2026-07-20

- site_audit 扩到 30 项检查：图片、GEO、i18n、性能

## v1.2.0 — 2026-07-17

- 8 → 13 个工具：keyword_cluster、search_intent、kgr_auto、content_matrix、onpage_audit

## v1.0.0 — 2026-06-25

- 首次公开发布：8 个免费 CLI 工具、零依赖、双语文档
