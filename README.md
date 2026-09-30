# LLM Wiki

> 把一篇篇源文档「编译」成一个持续维护、互相链接的 Markdown 知识库，并支持基于它的问答。
> 与每次查询都重新检索的传统 RAG 相反：**知识只编译一次，之后持续维护**。

本项目是 [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) 的 **Python 最小实现**。
原项目以「Agent Skill（Markdown 指令）」为程序本体，由 Claude Code / Codex 等编码智能体直接执行；
本仓库把它落成**可以用 Python 直接跑**的版本，便于学习其架构与主链路。

---

## 1. 当前版本：M0 + M1

版本按「最小实现 → 完整实现」分阶段构建。截至当前，已完成前两个阶段：

| 阶段 | 名称 | 内容 | 状态 |
|---|---|---|---|
| **M0** | 最小闭环 | `ingest` 写入 + `query` 读取，靠 `index.md` 联动 | ✅ 已完成 |
| **M1** | 写入前校验 | 结构化 JSON 容错 + 断链拦截 + `overview` 写入 | ✅ 已完成 |
| M2 | 结构体检 | `health.py`：零 LLM 的确定性检查 | ⬜ 未开始 |
| M3 | 图谱 Pass1 | `build_graph.py`：由 `[[wikilink]]` 建边 | ⬜ 未开始 |
| M4 | 图谱 Pass2 + 社区 | LLM 推断边 + Louvain + 增量缓存 | ⬜ 未开始 |
| M5 | 语义质检 + 自愈 | `lint.py` + `heal.py` | ⬜ 未开始 |
| M6 | 增量与多格式 | `refresh.py` + `file_to_md.py` + `pdf2md.py` | ⬜ 未开始 |
| M7 | 触发与自动化 | 斜杠命令 + 定时同步 | ⬜ 未开始 |

### 一句话概括当前能力

- **写入（ingest）**：放进 `raw/` 一篇 `.md` → 一条命令 → 编译出 `sources/` `entities/` `concepts/` 若干页面，并自动更新 `index.md` / `log.md` / `overview.md`。
- **读取（query）**：一个问题 → 词频召回相关页 → 交给 LLM 带 `[[引用]]` 回答。
- **写入前校验（M1）**：模型返回的 JSON 先做结构容错，再拦截「断链」，不合格则整批不落盘。

---

## 2. 技术栈

| 类别 | 技术 | 用途 |
|---|---|---|
| 语言 | Python 3.10–3.13 | 工具脚本 |
| LLM 网关 | [litellm](https://github.com/BerriAI/litellm) | 统一调用各厂商模型（当前默认 DeepSeek） |
| 默认模型 | `deepseek/deepseek-chat` | 编译与问答的主模型 |
| 数据层 | Markdown + 文件系统 | **无数据库**：知识全部落盘为 `.md` |
| 依赖 | 标准库（`re` / `json` / `pathlib` / `hashlib`） | 解析、路径、哈希 |
| 前端 | 无 | 本项目只含 `tools/` 脚本 |

> 设计哲学：**零重型依赖**。除 `litellm` 外，召回、校验、索引、日志全部用标准库实现，任何机器都能跑。

---

## 3. 目录结构

```
llm-wiki/
├── raw/                     # 不可变的源文档（输入区）
├── wiki/                    # 生成的知识层（输出区）
│   ├── sources/             # 源文档摘要页（kebab-case.md）
│   ├── entities/            # 实体页（TitleCase.md）
│   ├── concepts/            # 概念页（TitleCase.md）
│   ├── index.md             # 页面索引（ingest 写、query 读）
│   ├── log.md               # 操作日志（最新在前）
│   └── overview.md          # 全局综述
├── tools/
│   ├── _utils.py            # 共享底座：路径 / LLM / 哈希 / 写盘 / 索引 / 日志
│   ├── ingest.py            # 写入侧：把源文档编译进知识库
│   └── query.py             # 读取侧：召回 + 综合回答
├── CLAUDE.md                # Schema：页面格式与工作流定义（模型约束）
└── README.md
```

**命名约定**（来自 Schema）：

- **source 页** → `kebab-case.md`，与源文件名一致，如 `raw/rag.md` → `sources/rag.md`
- **entity / concept 页** → `TitleCase.md`，且**文件名与 `[[链接名]]` 一致**，如 `concepts/RAG.md`

---

## 4. 整体数据流

以 `index.md` 为唯一耦合点：**ingest 写它，query 读它**。

```
                               ┌─────────────────────────────────────────┐
                               │                wiki/ (文件系统)           │
                               │  sources/  entities/  concepts/           │
                               │  index.md   log.md   overview.md          │
                               └─────────────────────────────────────────┘
                                     ▲                          │
                 写入：write_page    │                          │  读取：读页面正文
                 append_index/log    │                          ▼
┌──────────────┐    ┌────────────┐   │            ┌────────────────────────────┐
│ raw/*.md     │───▶│ ingest.py  │───┘            │ query.py                    │
│ (源文档)     │    │            │                │  1 读 index.md              │
└──────────────┘    │ 1 读源文档  │                │  2 词频召回 top15           │
                    │ 2 读 Schema │                │  3 拼上下文                 │
┌──────────────┐    │ 3 读 index  │                │  4 LLM 带引用回答            │
│ CLAUDE.md    │───▶│ 4 LLM→JSON │                └────────────────────────────┘
│ (Schema)     │    │ 5 断链校验  │                          ▲
└──────────────┘    │ 6 写页面    │                ┌──────────────┐
                    │ 7 更新索引  │                │ 用户问题      │
                    │   与日志    │                └──────────────┘
                    └────────────┘
```

### 两条主链路

**A. 写入链路（ingest）**

```
raw/<doc>.md
   │  ① 读源文件（字符串）
   │  ② 读 Schema CLAUDE.md（约束）
   │  ③ 读 wiki/index.md（现有页面清单）
   ▼
拼成 user prompt： schema + 现有索引 + 源文档
   │  ④ call_llm(json_mode=True) → 模型返回结构化 JSON
   ▼
JSON { title, source_page, entity_pages[], concept_pages[], overview_update, log_entry }
   │  ⑤ validate_links() 校验断链 —— 失败即 return，磁盘零改动
   ▼  ⑥ 通过则逐页 write_page()
wiki/sources|entities|concepts/*.md  +  overview.md
   │  ⑦ append_index() 合并去重  →  index.md
   │     append_log()   前插      →  log.md
   ▼
完成
```

**B. 读取链路（query）**

```
用户问题
   │  ① 读 wiki/index.md → 用正则抠出所有页面路径
   │  ② find_relevant_pages()：英文分词 + 中文 2-gram → 词频打分 → top15
   │  ③ 读取这 15 页正文，拼成上下文
   ▼  ④ call_llm()（自由文本，不带 json_mode）→ 带 [[引用]] 的回答
回答
```

---

## 5. 快速开始

### 环境要求

- Python 3.10 ≤ 版本 < 3.14
- 一个 DeepSeek API Key（在 [platform.deepseek.com](https://platform.deepseek.com) 生成）

### 安装

```bash
git clone https://github.com/NotFoundThisName/llm-wiki.git
cd llm-wiki
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
# source .venv/bin/activate
pip install litellm
```

### 配置

在**同一个终端会话**里设置 Key（Windows 用户注意 `NO_PROXY` 里若含 `[::1]`，`_utils.py` 会自动清理）：

```powershell
# PowerShell（仅当前会话）
$env:DEEPSEEK_API_KEY="sk-你的真实key"
$env:PYTHONIOENCODING="utf-8"     # 消除控制台中文乱码
```

```bash
# Git Bash / macOS / Linux
export DEEPSEEK_API_KEY="sk-你的真实key"
export PYTHONIOENCODING="utf-8"
```

可选环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 无（必填） | API 密钥 |
| `LLM_MODEL` | `deepseek/deepseek-chat` | 覆盖默认模型 |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | 覆盖 API 端点 |

### 运行

```bash
# 写入：把一个源文档编译进知识库（路径相对 raw/，不带 raw/ 前缀）
python -m tools.ingest "4-re.md"

# 读取：对知识库提问
python -m tools.query "升级前配置怎么比对"
```

> **必须用 `python -m tools.xxx`**，不能 `python tools/xxx.py`，因为代码里用的是
> `from tools._utils import ...`，按文件直接运行会找不到 `tools` 包。

---

## 6. 方法详解

### `tools/_utils.py` —— 共享底座

所有工具都单向依赖它。以下方法按出现顺序。

#### `safe_rel_path(rel: str) -> str`

| 项 | 内容 |
|---|---|
| **输入** | LLM 返回的原始路径字符串，如 `"wiki/sources/What is RAG?.md"` |
| **输出** | 规范化后的安全相对路径，如 `"sources/What is RAG-.md"` |
| **作用** | 统一分隔符；剥掉模型多写的 `wiki/` 前缀（防 `wiki/wiki/`）；过滤 `..` 防目录穿越；替换 Windows 非法字符 `<>:"/\|?*`；去尾部空格/点；补 `.md`；全空时兜底 `untitled.md` |

#### `sha256(text: str) -> str`

| 项 | 内容 |
|---|---|
| **输入** | 任意字符串 |
| **输出** | 64 位十六进制哈希（字符串） |
| **作用** | 内容去重 / 增量判断的基础：内容不变则哈希相同（供后续 M6 使用） |

#### `call_llm(system, user, model=MODEL, json_mode=False) -> str`

| 项 | 内容 |
|---|---|
| **输入** | `system`（系统提示，定角色/约束）、`user`（用户内容，通常含 schema+索引+源文）、`model`（模型名）、`json_mode`（是否要求 JSON） |
| **输出** | 首条回复的**文本内容**（`str`） |
| **作用** | 经 litellm 统一调用 LLM。对 DeepSeek 做特殊处理：显式传 `api_key`（避免空 token 401）、固定 `api_base`、仅在 `json_mode=True` 时加 `response_format={"type":"json_object"}` |

> ⚠️ `json_mode=True` 只用于 ingest 这类需要结构化输出的调用；**query 要自由文本，必须保持 `False`**，否则 DeepSeek 会因「prompt 中无 json 字样」返回 400。

#### `extract_wikilinks(text: str) -> list[str]`

| 项 | 内容 |
|---|---|
| **输入** | 任意文本 |
| **输出** | 所有 `[[名称]]` 的内部名称列表 |
| **作用** | 为断链校验提供「本页引用了谁」 |

#### `write_page(rel: str, content: str) -> Path`

| 项 | 内容 |
|---|---|
| **输入** | 相对路径 `rel`、页面正文 `content`（字符串） |
| **输出** | 写入后的**绝对路径**（`Path`） |
| **作用** | 先 `safe_rel_path` 规范化，再校验解析后的路径没有逃出 `wiki/`，自动建父目录，以 UTF-8 覆盖写入 |

> `content` 必须是 `str`。若模型把某个字段返回成对象，需在调用前取出正文（见 `ingest` 对 `overview_update` 的处理）。

#### `append_index(entrties: list[tuple[str, str, str]]) -> None`

| 项 | 内容 |
|---|---|
| **输入** | `[(分类, 标题, 相对路径), ...]`，分类取 `sources` / `entities` / `concepts` / `overview` |
| **输出** | 无返回值；重写 `wiki/index.md` |
| **作用** | 「解析旧内容 → 合并去重 → 整体重写」，**幂等**、可重复调用。分区顺序固定为 Sources / Entities / Concepts / Overview |

#### `append_log(entry: str) -> None`

| 项 | 内容 |
|---|---|
| **输入** | 一条日志文本 |
| **输出** | 无返回值；更新 `wiki/log.md` |
| **作用** | **前插（最新在最上面）**。首次写入时补 `# 日志` 一级标题；已有标题则保留标题、新条目插在其下 |

#### `parse_json_from_response(text: str) -> dict`

| 项 | 内容 |
|---|---|
| **输入** | LLM 的原始回复文本（可能带 ```` ```json ```` 围栏、前后夹解释文字） |
| **输出** | 解析出的第一个 JSON 对象（`dict`） |
| **作用** | 剥围栏 → 用 `json.JSONDecoder().raw_decode()` 只解析**第一个完整 JSON 对象**，自动忽略其后的多余内容（避免 `Extra data` 报错）。找不到则抛 `ValueError` |

#### 常量

| 名称 | 值 / 含义 |
|---|---|
| `ROOT` | 仓库根目录 |
| `RAW_DIR` / `WIKI_DIR` | `raw/` 与 `wiki/` |
| `INDEX` / `LOG` | `wiki/index.md` / `wiki/log.md` |
| `SCHEMA_FILE` | `CLAUDE.md`（Schema） |
| `MODEL` | `deepseek/deepseek-chat`（可被 `LLM_MODEL` 覆盖） |
| `INDEX_SECTIONS` | 四个分区及其标题 |

---

### `tools/ingest.py` —— 写入侧

#### `validate_links(out: dict, index: str) -> list[str]`

| 项 | 内容 |
|---|---|
| **输入** | `out`：模型返回并解析后的 dict；`index`：`index.md` 全文 |
| **输出** | 断链信息列表；**空列表 = 通过** |
| **作用** | 写入前的「断链」校验（确定性，不花 token）。构造「允许被链接到的名字」白名单 `titles`，逐个比对页面正文里的 `[[目标]]`，不在白名单里的记为断链 |

**白名单 `titles` 的四路来源**：

| # | 来源 | 例子 | 理由 |
|---|---|---|---|
| ① | 本次源页标题 | `检索增强生成` | 源页文件名是 kebab，标题可能是中文，两者不同 |
| ② | 每页文件名 stem | `rag-basics` | 兼容 `[[x]]` 写法 |
| ③ | 每页 `.md` 全名 | `rag-basics.md` | 兼容 `[[x.md]]` 写法 |
| ④ | `index.md` 已有页面 | 显示标题 + 路径 stem | 允许链接到以前 ingest 过的旧页 |

比对时 `[[A|别名]]` 只比较 `A`。

**为什么必须在写盘前做**：断链一旦落盘就难以回滚（分不清哪些是本批新增）。先校验、失败即 `return`，磁盘零改动——把每次 ingest 变成一次**事务**。

**断链样例输出**：

```
断链：sources/rag-basics.md → [[量子力学]]
断链：concepts/量子纠缠.md → [[量子力学]]
```

#### `main(raw_path: str) -> None`

| 项 | 内容 |
|---|---|
| **输入** | 相对 `raw/` 的源文档路径，如 `"4-re.md"` |
| **输出** | 无返回值；副作用是生成 `wiki/` 下的页面与索引/日志/综述，并打印 `ingested: <标题>` |
| **作用** | 编排整条写入链路 |

**执行步骤**：

1. 读源文件（`RAW_DIR / raw_path`）
2. 读 Schema（`CLAUDE.md`）
3. 读现有 `index.md`（不存在则视为空串）
4. `call_llm(PROMPT, schema+索引+源文, json_mode=True)` → `parse_json_from_response()`
5. **`validate_links()` 校验** —— 有断链则打印并 `return`（此时尚未写盘）
6. 写 `source_page` → `sources/`；收集 `(分类, 标题, 相对路径)`
7. 写 `entity_pages[]` → `entities/`
8. 写 `concept_pages[]` → `concepts/`
9. 若存在 `overview_update`，写 `overview.md`（兼容它被返回成对象的情况）
10. `append_index(written)` + `append_log(...)`

**命令**：

```bash
python -m tools.ingest "4-re.md"
```

**模型返回的 JSON 结构（数据契约）**：

```json
{
  "title": "检索增强生成",
  "source_page": {
    "path": "sources/rag.md",
    "content": "---\ntitle: \"检索增强生成\"\n---\n## Summary\n……\n## Connections\n- [[向量数据库]]"
  },
  "entity_pages": [
    { "path": "entities/Embedding.md", "content": "…… [[向量数据库]]" }
  ],
  "concept_pages": [
    { "path": "concepts/RAG.md", "content": "…… [[向量数据库]]" }
  ],
  "overview_update": "全局综述的新版本……",
  "log_entry": "## [2026-09-14] ingest | 检索增强生成"
}
```

---

### `tools/query.py` —— 读取侧

#### `find_relevant_pages(question: str, index: str) -> list[str]`

| 项 | 内容 |
|---|---|
| **输入** | `question`：用户问题；`index`：`index.md` 全文 |
| **输出** | 按得分降序的页面相对路径列表，**最多 15 页** |
| **作用** | 用词频给页面打分做**粗排召回**，不做向量/语义检索 |

**步骤**：

1. 从 `index` 正则抠出所有 `](路径.md)` 的路径
2. 英文/数字分词（小写），去重成关键词集合
3. 补中文**二元滑窗（2-gram）**：`升级前配置` → `{升级, 级前, 前配, 配置}`
4. 每页统计关键词出现总次数作为得分
5. 按得分降序取前 15

> 语义理解不在这里，而在下游 LLM：召回只负责「捞出一批候选」。

#### `main(question: str) -> None`

| 项 | 内容 |
|---|---|
| **输入** | 用户问题字符串 |
| **输出** | 无返回值；打印 LLM 的回答（带 `[[引用]]`） |
| **作用** | 读索引 → 召回 → 拼上下文 → 调用 LLM 生成回答 |

**命令**：

```bash
python -m tools.query "升级前配置怎么比对"
```

---

## 7. 数据契约速查

| 阶段 | 输入形式 | 输出形式 | 存档位置 |
|---|---|---|---|
| `ingest` | `raw/<doc>.md` 文本 | 多篇页面 + 索引/日志/综述 | `wiki/` |
| `validate_links` | `dict` + `index` 文本 | `list[str]`（空=通过） | 无（纯计算） |
| `write_page` | 相对路径 + 正文 `str` | 绝对 `Path` | `wiki/<path>` |
| `append_index` | `[(分类, 标题, 路径), ...]` | 重写 | `wiki/index.md` |
| `append_log` | 日志 `str` | 前插 | `wiki/log.md` |
| `find_relevant_pages` | 问题 + `index` 文本 | `list[str]`（≤15） | 无（纯计算） |
| `query` | 问题 `str` | 回答文本 | 无（打印） |

**`index.md` 的格式**：

```markdown
# 索引

## Sources
- [检索增强生成（RAG）](sources/rag.md)

## Entities
- [env_config.ini](entities/env_config.ini.md)

## Concepts
- [RAG](concepts/RAG.md)

## Overview
- [Overview](overview.md)
```

---

## 8. 已知边界与后续路线

**当前边界（M0+M1）**

- 召回是**词频**，不是语义：同义词/改写会漏召回（如只写"幻觉"的页，问"胡编乱造"召回不到）。
- 无去重判断：重 ingest 同一文档会**整篇覆盖**页面。
- 无图形化、无增量、无多格式解析、无自愈。

**后续阶段**（见第 1 节表格）：M2 结构体检 → M3/M4 图谱 → M5 语义质检与自愈 → M6 增量与多格式 → M7 自动化。

**安全提示**

- 不要把 API Key 写进任何文件或提交到仓库；用环境变量传入。
- `wiki/log.md` 可能出现双标题（模型 `log_entry` 自带 `##`，`append_log` 又加时间戳），待优化。

---

## 9. 许可证

本仓库为学习用实现，参考 [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent)（MIT）。
