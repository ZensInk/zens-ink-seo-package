# 更新日志

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
