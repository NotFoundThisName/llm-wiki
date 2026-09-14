# tools/ingest.py
# ingest（编译）：把一个源文档「编译」进知识库。
# 流程：读源文件 → 读 Schema 约束 → 读现有索引 → 调 LLM 返回结构化 JSON
#       → 写 sources/entities/concepts 页面 → 更新 index.md 与 log.md
# 是整个 M0 最小闭环的写入侧。

import json
import sys
from pathlib import Path

from tools._utils import RAW_DIR, SCHEMA_FILE, INDEX, call_llm, write_page, append_index, append_log, WIKI_DIR

# 指令模板：告诉模型「只返回 JSON」，并约定字段名与页面结构。
# 注意字段名是复数 entity_pages / concept_pages，后面解析时要用对。
PROMPT = """你在维护一个 Markdown 知识库。
严格返回一个 JSON 对象，不要解释、不要代码围栏。
字段：title, source_page, entity_pages[], concept_pages[], log_entry
每个页面形如 {path, content}，content 用 [[wikilink]] 互链。"""


def parse_json(text: str) -> dict:
    """
    把模型返回的文本解析成 dict。
    模型常把 JSON 包在代码围栏里，形如：

        ```json
        {"a": 1}
        ```

    所以先去掉首尾空白；若以 ``` 开头，则去掉第一行围栏和结尾的 ```。
    :param text: LLM 返回的原始文本
    :return: 解析后的 dict
    """
    text = text.strip()
    if text.startswith('```'):
        # split("\n",1)[1] 取第一行之后的内容；rsplit("```",1)[0] 截掉结尾围栏
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def main(raw_path: str) -> None:
    # 1. 读取源文件（相对 raw/ 的路径）
    raw = (RAW_DIR / raw_path).read_text(encoding="utf-8")

    # 2. 读取 Schema，主要是拿页面格式、命名、互链等硬约束
    schema = SCHEMA_FILE.read_text(encoding="utf-8")

    # 3. 读取现有索引，让模型知道已有哪些页面，避免重复生成、并复用已有 [[wikilink]]
    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""

    # 4. 调用 LLM 并解析返回的 JSON
    out = parse_json(call_llm(
        PROMPT,
        f"{schema}\n\n# 现有索引\n{index}\n\n# 源文档\n{raw}"
        )
    )

    # out 的结构大致如下：
    # {
    #     "title": "Python",
    #     "source_page": {
    #         "path": "wiki/python.md",
    #         "content": "# Python\n..."
    #     },
    #     "entity_pages": [
    #         {"path": "wiki/guido-van-rossum.md", "content": "..."}
    #     ],
    #     "concept_pages": [
    #         {"path": "wiki/dynamic-typing.md", "content": "..."}
    #     ],
    #     "log_entry": "..."
    # }

    # 5. 写源页面，并收集 (分类, 标题, 相对路径) 供更新索引。
    #    关键：索引里必须存「相对 wiki/ 的路径」，所以用 write_page 的返回值
    #    （它已过 safe_rel_path 规范化）再 relative_to(WIKI_DIR)，而不是直接用模型给的 path。
    page = write_page(out["source_page"]["path"], out["source_page"]["content"])
    written = [("sources", out["title"], page.relative_to(WIKI_DIR).as_posix())]

    # 6. 写实体页面。标题用文件名主体（Path(p).stem 去掉扩展名），与索引分区名一致
    for p in out["entity_pages"]:
        page = write_page(p["path"], p["content"])
        written.append(("entities", Path(p["path"]).stem, page.relative_to(WIKI_DIR).as_posix()))

    # 7. 写概念页面
    for p in out["concept_pages"]:
        page = write_page(p["path"], p["content"])
        written.append(("concepts", Path(p["path"]).stem, page.relative_to(WIKI_DIR).as_posix()))

    # 8. 更新索引与日志：index.md 合并去重，log.md 前插最新条目
    append_index(written)
    append_log(out.get("log_entry") or f"ingest {out['title']}")

    print("ingested:", out["title"])


if __name__ == "__main__":
    # 用法：python -m tools.ingest "相对raw的路径.md"
    main(sys.argv[1])
