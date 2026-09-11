import re

from tools._utils import WIKI_DIR, INDEX, call_llm


def find_relevant_pages(question:str,index:str)->list[str]:
    """
    主要是词频匹配
    :param question:
    :param index:
    :return:
    """
    # 1.从字符串 index 中，用正则找出所有 Markdown 链接里指向 .md 文件的路径   [显示文本](路径.md)
    path=re.findall(r"\]\(([^)]+\.md)\)",index)

    # 2. 简单的英文/数字分词，并去重得到一个关键词集合
    tokens=set(re.findall(r"[a-z0-9]+",question.lower()))

    # 3. 在之前英文分词的基础上，补充中文的二元字符滑窗（2-gram），用来支持中文检索
    tokens |= {question[i:i+2] for i in range(0,len(question)-1)}

    scoreds=[]
    for p in path:
        text=(WIKI_DIR/p).read_text(encoding="utf-8").lower()
        score = sum(text.count(t) for t in tokens)
        if score:
            scoreds.append((score,p))
    scoreds.sort(reverse=True)
    return [p for _,p in scoreds[:15]]

def main(question:str)->None:
    index = INDEX.read_text(encoding="utf-8")
    pages=find_relevant_pages(question,index)
    context="\n\n".join((WIKI_DIR/p).read_text(encoding="utf-8") for p in pages)
    print(call_llm(
        "只用给定页面回答，引用时写成 [[页面名]]。",
        f"# 上下文\n{context}\n\n# 问题\n{question}"
    ))