import json
import sys

from tools._utils import RAW_DIR, SCHEMA_FILE, INDEX, call_llm, write_page

PROMPT = """你在维护一个 Markdown 知识库。
严格返回一个 JSON 对象，不要解释、不要代码围栏。
字段：title, source_page, entity_pages[], concept_pages[], log_entry
每个页面形如 {path, content}，content 用 [[wikilink]] 互链。"""

def parse_json(text:str)->dict:
    """
    因为模型通常返回是这种
    \n\n```json
    {"a": 1}
    ```\n
    所以先去点前后空格
    :param text: 输入的文本
    :return: 输出解析好的json
    """
    text = text.strip()
    if text.startswith('```'):
        text = text.split("\n",1)[1].rsplit("```",1)[0]
    return json.loads(text)

def main(raw_path:str)->None:
    # 1、读取源文件
    raw = (RAW_DIR / raw_path).read_text(encoding="utf-8")
    # 2.读取schema ， 主要是约束格式
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    # 3.读取现有索引，目的是让模型直到现在有哪些页面，避免重复生成，或者让它复用已有的 Wiki 链接（比如 [[Python]] 指向已有页面）。
    index = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
    #4. 调用LLM + 解析json
    out = parse_json(call_llm(
        PROMPT,
        f"{schema}\n\n# 现有索引\n{index}\n\n# 源文档\n{raw}"
        )
    )
    # out最后类似于这种
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
    #     ]
    # }
    # 5. 写源页面
    write_page(out["source_page"]["path"], out["source_page"]["content"])
    # 6. 写实体页和概念页
    # entity_pages：实体页，比如人物、公司、工具
    # concept_pages：概念页，比如术语、算法、设计模式
    for p in out["entity_pages"] + out["concept_pages"]:
        write_page(p["path"],p["content"])
    print("ingested:", out["title"])

if __name__ == "__main__":
    main(sys.argv[1])