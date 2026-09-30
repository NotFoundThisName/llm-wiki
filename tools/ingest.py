# tools/ingest.py
# ingest（编译）：把一个源文档「编译」进知识库。
# 流程：读源文件 → 读 Schema 约束 → 读现有索引 → 调 LLM 返回结构化 JSON
#       → 写 sources/entities/concepts 页面 → 更新 index.md 与 log.md
# 是整个 M0 最小闭环的写入侧。

import re
import sys
from pathlib import Path

from tools._utils import RAW_DIR, SCHEMA_FILE, INDEX, call_llm, write_page, append_index, append_log, WIKI_DIR, \
    parse_json_from_response, safe_rel_path, extract_wikilinks

# 指令模板：告诉模型「只返回 JSON」，并约定字段名与页面结构。
# 注意字段名是复数 entity_pages / concept_pages，后面解析时要用对。
PROMPT = """你在维护一个 Markdown 知识库。
严格返回一个 JSON 对象，不要解释、不要代码围栏。
字段：title, source_page, entity_pages[], concept_pages[], overview_update, log_entry
每个页面形如 {path, content}，content 用 [[wikilink]] 互链。"""

def validate_links(out: dict, index: str) -> list[str]:
    """
    写入前的「断链」校验（确定性，不花 token）。

    模型在页面 content 里会写 [[wikilink]]，但它引用的目标可能根本不存在，例如：
        量子纠缠是一种 [[量子力学]] 现象，最早由 [[爱因斯坦]] 等人提出质疑。
    如果「量子力学」既不在本次要写入的页面里，也不在历史 index 中，这条链接就是
    断链（dead link），会污染索引，并让后续的图谱/检索出现悬空节点。

    做法：先构造一份「允许被链接到的名字」白名单 titles，再逐个比对 content 里的
    [[目标]]，不在白名单里的记为断链。白名单四路来源：
        ① 本次源页标题          （源页文件名是 kebab，标题可能是中文，两者不同）
        ② 每页文件名 stem       （兼容 [[x]] 写法，如 rag-basics）
        ③ 每页 .md 全名         （兼容 [[x.md]] 写法）
        ④ index.md 已有页面      （允许链接到以前 ingest 过的旧页：显示标题 + 路径 stem）

    :param out:   模型返回并已解析的 dict（含 source_page / entity_pages / concept_pages）
    :param index: index.md 的全文，用来收集历史已存在的页面名
    :return: 断链信息列表；空列表表示校验通过
    """
    # 断链信息收集处，每发现一条就 append 一条描述
    errors=[]
    # 把本批要写入的所有页面拍平成一个列表，便于统一遍历
    pages=[out["source_page"],*out["entity_pages"],*out["concept_pages"]]
    # 白名单：允许被 [[链接]] 指向的名字集合，先放入本批源页的标题
    titles={out["title"]}

    for page in pages:
        # 收集本批每个页面文件名的主体与全名，兼容 [[x]] 与 [[x.md]] 两种写法
        rel = safe_rel_path(page["path"])
        titles.add(Path(rel).stem)
        titles.add(Path(rel).name)
    # 再并上历史 index 里已存在的页面（显示标题 + 路径 stem），允许链接旧页面
    for title,path in re.findall(r"- \[(.+?)\]\(([^)]+\.md)\)",index):
        titles.add(title)
        titles.add(Path(safe_rel_path(path)).stem)

    # 逐个检查本批页面正文里的每一个 [[链接]]
    for p in pages:
        for row in extract_wikilinks(p["content"]):
            target = row.split("|",1)[0].strip()   # [[A|别名]] 只比较 A
            if target not in titles:
                errors.append(f"断链：{p['path']} → [[{row}]]")
    return errors



def main(raw_path: str) -> None:
    # 1. 读取源文件（相对 raw/ 的路径）
    raw = (RAW_DIR / raw_path).read_text(encoding="utf-8")

    # 2. 读取 Schema，主要是拿页面格式、命名、互链等硬约束
    schema = SCHEMA_FILE.read_text(encoding="utf-8")

    # 3. 读取现有索引，让模型知道已有哪些页面，避免重复生成、并复用已有 [[wikilink]]
    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""

    # 4. 调用 LLM 并解析返回的 JSON。
    #    json_mode=True：ingest 需要结构化输出，让 DeepSeek 强制返回 JSON 对象。
    #    （query 要自由文本，不能传这个参数，否则 400。）
    out = parse_json_from_response(call_llm(
        PROMPT,
        f"{schema}\n\n# 现有索引\n{index}\n\n# 源文档\n{raw}",
        json_mode=True
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

    # 写入之前断链校验
    if (errors := validate_links(out,index)):
        print("校验失败，中止写入：")
        for error in errors:
            print(" -",error)
        return

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

    if (overview := out.get("overview_update")):       # 缺字段也不崩
        # 模型可能把它写成 {path, content} 对象；write_page 只收 str，先取出正文
        text = overview.get("content") if isinstance(overview, dict) else overview
        write_page("overview.md", text)
        written.append(("overview", "Overview", "overview.md"))

    # 8. 更新索引与日志：index.md 合并去重，log.md 前插最新条目
    append_index(written)
    append_log(out.get("log_entry") or f"ingest {out['title']}")

    print("ingested:", out["title"])


if __name__ == "__main__":
    # 用法：python -m tools.ingest "相对raw的路径.md"
    main(sys.argv[1])
