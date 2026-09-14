# tools/query.py
# query（查询）：针对一个问题，从 wiki 里召回相关页面并让 LLM 综合回答。
# 召回是「词频粗排」，真正的语义理解交给下游 LLM。
# 完整版还会在此之上接 graph.json 做邻居扩展（本文件是最小实现，尚未接入）。

import re
import sys

from tools._utils import WIKI_DIR, INDEX, call_llm


def find_relevant_pages(question: str, index: str) -> list[str]:
    """
    用词频给页面打分，返回得分最高的若干页面的相对路径（最多 15 页）。
    支持英文/数字分词 + 中文二元滑窗，属于轻量召回，不做向量/语义检索。
    :param question: 用户问题
    :param index: index.md 的全文（从中提取所有页面链接）
    :return: 按得分从高到低排序的页面相对路径列表
    """
    # 1. 从 index 中提取所有指向 .md 的 Markdown 链接路径，形如 [显示文本](路径.md)
    path = re.findall(r"\]\(([^)]+\.md)\)", index)

    # 2. 简单英文/数字分词（转小写后按字母数字切），并去重得到关键词集合
    tokens = set(re.findall(r"[a-z0-9]+", question.lower()))

    # 3. 补充中文的二元字符滑窗（2-gram），用来支持中文检索。
    #    例：「升级前配置」→ {升级, 级前, 前配, 配置}。粗粒度但零依赖。
    tokens |= {question[i:i + 2] for i in range(0, len(question) - 1)}

    # 4. 对每个候选页面统计关键词出现总次数作为得分
    scoreds = []
    for p in path:
        text = (WIKI_DIR / p).read_text(encoding="utf-8").lower()
        score = sum(text.count(t) for t in tokens)   # 命中越多分越高
        if score:
            scoreds.append((score, p))

    # 5. 按得分降序，取前 15 页
    scoreds.sort(reverse=True)
    return [p for _, p in scoreds[:15]]


def main(question: str) -> None:
    # 读取索引 → 词频召回相关页 → 拼接上下文 → 交给 LLM 带引用回答
    index = INDEX.read_text(encoding="utf-8")
    pages = find_relevant_pages(question, index)
    context = "\n\n".join((WIKI_DIR / p).read_text(encoding="utf-8") for p in pages)
    print(call_llm(
        "只用给定页面回答，引用时写成 [[页面名]]。",
        f"# 上下文\n{context}\n\n# 问题\n{question}"
    ))


if __name__ == "__main__":
    # 用法：python -m tools.query "你的问题"
    main(sys.argv[1])
