# 更新日志

## v1.6.1 — 2026-08-23

**site_audit 新增 agent-readiness 检查。** 网站越来越多地被自主 agent 阅读，而不只是人和爬虫。`site_audit` 现在会标记 llms.txt 里决定 agent 能否理解你产品的两个缺口：

- **新检查：agent when-to-use** —— llms.txt 没有 `When to use` 段落时只是营销文案而非指引，agent 判断不出你的站适合什么任务。警告级别，附修复提示。
- **新检查：agent how-to-call** —— llms.txt 没有安装命令 / 端点 / MCP 入口时，agent 发现了你也没法调用。信息级别。
- 两项检查均为确定性规则、零依赖，跑在现有 `site_audit` 流程里，不需要新参数。
- 已用生产构建验证：完整 llms.txt 干净通过；删掉 when-to-use 段落后正确触发警告。

背景：本次与 ZensInk Pro v2.4.0 同步发布——Pro 新增完整 Agent Readiness 评分（8 项检查、0-100 分、P0/P1/P2 修复方案）。该清单的参考实现让 zens.ink 在 [is-agentic.com](https://is-agentic.com/scan/zens.ink) 从 64 分升到 98 分。

## v1.6.0 — 2026-08-22

**kd 品牌词指纹。** 品牌词会污染通用 KD 分数——本版本检测品牌词并只对可竞争席位重算难度。

- 品牌三重指纹：官方域名进 top3、域名家族占位 ≥2、平台生态密度
- `kd_entry`：剔除官方页与平台固定位后的截流难度
- KD → 引用域外链预算曲线（编辑型/目录型双轨）
- `--markdown` 自包含报告模式

## v1.5.0 — 2026-07-17

- **GEO Score** —— 单页 AI 引用就绪度：5 层（事实 35% / 结构 25% / 语义 15% / AI 可达 15% / 信任 10%），确定性 0-100 分 + 字母等级 + P0/P1/P2 行动方案。零 API 成本。
- **MCP stdio server** —— `zens-ink mcp` 把所有 CLI 工具暴露给 MCP 客户端（DSH、Claude、Codex）。

## v1.4.x — 2026-06/07

- v1.4.2：MCP stdio server
- v1.4.1：33 项 site_audit（链接 / meta / 图片 / GEO / i18n / staging 泄漏检测）
- v1.4.0：search_intent 四分类、onpage_audit 7 维评分、full_audit 12 步编排

## v1.3.x — 2026-06

- serp_intent：Serper 驱动的 SERP 意图评估（20+ 页面类型、4 种意图、SERP 特征检测）
- Winability Score、Content Radar、Competitor Radar（与 Pro 同步的方法论）

## v1.1.0 — 2026-06-25

- 首次公开发布：关键词发现、搜索量、KD、GSC 表现、竞品缺口、KGR、聚类
