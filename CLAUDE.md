# LLM Wiki Agent —— Schema 与工作流指令

本 Wiki 完全由 Claude Code 维护。无需 API key，也无需 Python 脚本——只需在 Claude Code 中打开本仓库并与它对话即可。

## 斜杠命令（Claude Code）

| 命令 | 你说的话 |
|---|---|
| `/wiki-ingest` | `ingest raw/my-article.md` |
| `/wiki-query` | `query: 主要主题是什么？` |
| `/wiki-health` | `health`（快速，每次会话都跑） |
| `/wiki-lint` | `lint the wiki`（昂贵，周期性执行） |
| `/wiki-graph` | `build the knowledge graph` |

或者直接用自然语言描述你的需求：
- *"导入这个文件：raw/papers/attention-is-all-you-need.md"*
- *"Wiki 里关于 transformer 模型是怎么说的？"*
- *"检查 Wiki 中的孤立页面和矛盾之处"*
- *"构建图谱并展示与 RAG 相关的内容"*

Claude Code 会自动读取本文件，并遵循下述工作流。

---

## 目录结构

```
raw/          # 不可变的源文档——永远不要修改
wiki/         # 由 Claude 完全掌控这一层
  index.md    # 所有页面的目录——每次 ingest 时更新
  log.md      # 只追加（append-only）的时间顺序记录
  overview.md # 跨所有来源的持续演进的综合概述
  sources/    # 每个源文档对应一个摘要页面
  entities/   # 人物、公司、项目、产品
  concepts/   # 想法、框架、方法、理论
  syntheses/  # 已保存的查询答案
graph/        # 自动生成的图谱数据
tools/        # 独立的 Python 脚本
  health.py   # 结构检查（确定性，不调用 LLM）
  lint.py     # 内容质量检查（使用 LLM 做语义分析）
  build_graph.py  # 知识图谱生成
```

---

## 页面格式

每个 Wiki 页面都使用以下 frontmatter：

```yaml
---
title: "Page Title"
type: source | entity | concept | synthesis
tags: []
sources: []       # 影响本页面的源文档 slug 列表
last_updated: YYYY-MM-DD
---
```

使用 `[[PageName]]` wikilink 链接到其他 Wiki 页面。

---

## Ingest（导入）工作流

触发方式：*"ingest <file>"* 或 `/wiki-ingest`

**支持的格式：** Markdown（`.md`）直接导入。非 Markdown 文件（`.pdf`、`.docx`、`.pptx`、`.xlsx`、`.html`、`.txt`、`.csv`、`.json`、`.xml`、`.rst`、`.rtf`、`.epub`、`.ipynb`、`.yaml`、`.yml`、`.tsv`、`.wav`、`.mp3`）会先通过 [markitdown](https://github.com/microsoft/markitdown) 自动转换为 Markdown 再导入。使用 `--no-convert` 可跳过自动转换。

步骤（按顺序）：
1. 使用 Read 工具完整读取源文档（若为非 Markdown 则先自动转换）
2. 读取 `wiki/index.md` 和 `wiki/overview.md` 以获取当前 Wiki 上下文
3. 写入 `wiki/sources/<slug>.md`——使用下方的源文档页面格式
4. 更新 `wiki/index.md`——在 Sources 章节下添加条目
5. 更新 `wiki/overview.md`——如有必要则修订综合概述
6. 为文中提到的人物、公司、项目更新或创建 entity 页面
7. 为讨论的关键想法和框架更新或创建 concept 页面
8. 标记与现有 Wiki 内容存在的任何矛盾
9. 追加到 `wiki/log.md`：`## [YYYY-MM-DD] ingest | <Title>`
10. **导入后校验**——检查是否有损坏的 `[[wikilinks]]`，验证所有新页面都已收录于 `index.md`，并打印变更摘要

### 源文档页面格式

```markdown
---
title: "Source Title"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---

## Summary
2–4 句摘要。

## Key Claims
- 主张 1
- 主张 2

## Key Quotes
> "此处引用" — 上下文

## Connections
- [[EntityName]] — 它们如何关联
- [[ConceptName]] — 如何连接

## Contradictions
- 与 [[OtherPage]] 矛盾之处：...
```

### 领域专属模板

如果源文档属于某个特定领域（例如个人日记、会议记录），Agent 应使用专门的模板，而非上述默认的通用模板：

#### 日记 / 日志模板
```markdown
---
title: "YYYY-MM-DD Diary"
type: source
tags: [diary]
date: YYYY-MM-DD
---
## Event Summary
...
## Key Decisions
...
## Energy & Mood
...
## Connections
...
## Shifts & Contradictions
...
```

#### 会议记录模板
```markdown
---
title: "Meeting Title"
type: source
tags: [meeting]
date: YYYY-MM-DD
---
## Goal
...
## Key Discussions
...
## Decisions Made
...
## Action Items
...
```

---

## Query（查询）工作流

触发方式：*"query: <question>"* 或 `/wiki-query`

步骤：
1. 读取 `wiki/index.md` 以确定相关页面
2. 使用 Read 工具读取这些页面
3. 综合出答案，并使用 `[[PageName]]` wikilink 作为行内引用
4. 询问用户是否要将答案归档为 `wiki/syntheses/<slug>.md`

---

## Lint（检查）工作流

触发方式：*"lint the wiki"* 或 `/wiki-lint`

使用 Grep 和 Read 工具检查：
- **孤立页面（Orphan pages）**——没有来自其他页面的 `[[links]]` 入链的 Wiki 页面
- **损坏链接（Broken links）**——指向不存在页面的 `[[WikiLinks]]`
- **矛盾之处（Contradictions）**——跨页面相互冲突的表述
- **过时摘要（Stale summaries）**——在更新的源文档之后未再更新的页面
- **缺失的 entity 页面（Missing entity pages）**——在 3 个及以上页面中被提及、却没有独立页面的实体
- **数据缺口（Data gaps）**——Wiki 无法回答的问题；建议新的源文档

输出一份 lint 报告，并询问用户是否要保存到 `wiki/lint-report.md`。

---

## Health（健康检查）工作流

触发方式：*"health"* 或 `/wiki-health`

运行：`python tools/health.py`（或 `python tools/health.py --json` 以获取机器可读输出）

快速的结构完整性检查——**零 LLM 调用**，每次会话都可以安全运行：
- **空文件 / 残桩文件**——除 frontmatter 外没有内容的页面（限流导致的损坏）
- **索引同步（Index sync）**——`wiki/index.md` 的条目与磁盘上实际文件的对比
- **日志覆盖（Log coverage）**——在 `wiki/log.md` 中缺少对应 `ingest` 条目的源文档页面

输出一份 health 报告。使用 `--save` 写入 `wiki/health-report.md`。

### Health 与 Lint 的边界

| 维度 | `health` | `lint` |
|---|---|---|
| **范围** | 结构完整性 | 内容质量 |
| **LLM 调用** | 零 | 有（语义分析） |
| **成本** | 免费 | 消耗 token |
| **频率** | 每次会话，其他工作之前 | 每 10–15 次 ingest |
| **检查项** | 空文件、索引同步、日志同步 | 孤立页面、损坏链接、矛盾、缺口 |
| **工具** | `tools/health.py` | `tools/lint.py` |
| **运行顺序** | 最先（预检） | 在 health 通过之后 |

> 先运行 `health`——对空文件做 lint 只会浪费 token。

---

## Graph（图谱）工作流

触发方式：*"build the knowledge graph"* 或 `/wiki-graph`

当用户要求构建图谱时，运行 `tools/build_graph.py`，它会：
- 第一遍（Pass 1）：解析所有 `[[wikilinks]]` → 确定性的 `EXTRACTED` 边
- 第二遍（Pass 2）：推断隐含关系 → 带置信度分数的 `INFERRED` 边
- 运行 Louvain 社区发现
- 输出 `graph/graph.json` + `graph/graph.html`

如果用户尚未配置好 Python 及依赖，则改为手动生成图谱数据：
1. 使用 Grep 找出所有 Wiki 页面中的 `[[wikilinks]]`
2. 构建节点 / 边列表
3. 直接写入 `graph/graph.json`
4. 使用 vis.js 模板写入 `graph/graph.html`

---

## 命名约定

- 源文档 slug：`kebab-case`，与源文件名一致
- Entity 页面：`TitleCase.md`（例如 `OpenAI.md`、`SamAltman.md`）
- Concept 页面：`TitleCase.md`（例如 `ReinforcementLearning.md`、`RAG.md`）
- 源文档页面：`kebab-case.md`

## Index 格式

```markdown
# Wiki Index

## Overview
- [Overview](overview.md) — 持续演进的综合概述

## Sources
- [Source Title](sources/slug.md) — 一句话摘要

## Entities
- [Entity Name](entities/EntityName.md) — 一句话描述

## Concepts
- [Concept Name](concepts/ConceptName.md) — 一句话描述

## Syntheses
- [Analysis Title](syntheses/slug.md) — 它回答了什么问题
```

## Log 格式

每条记录都以 `## [YYYY-MM-DD] <operation> | <title>` 开头，因此可被 grep 解析：

```
grep "^## \[" wiki/log.md | tail -10
```

操作类型：`ingest`、`query`、`health`、`lint`、`graph`
