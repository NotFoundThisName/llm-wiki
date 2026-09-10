# 所有工具的唯一依赖：路径、LLM、哈希、wikilink
import hashlib
import os
import re
from pathlib import Path
from litellm import completion

ROOT=Path(__file__).resolve().parent.parent
RAW_DIR,WIKI_DIR=ROOT/"raw",ROOT/"wiki"
INDEX,LOG=WIKI_DIR/"index.md",WIKI_DIR/"log.md"
SCHEMA_FILE=RAW_DIR/"CLAUDE.md"
MODEL = os.getenv("LLM_MODEL", "claude-3-5-sonnet-latest")
WIKILINK_RE=re.compile(r"\[\[([^\]]+)\]\]")

def sha256(text:str)->str:
    """
    把字符串 text 按 UTF-8 编码后，计算它的 SHA-256 哈希值，并输出一个 十六进制字符串。
    :param text:
    :return:
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def call_llm(system:str,user:str,model:str = MODEL)->str:
    resp=completion(
        model=model,
        messages=[
            {"role":"system","content":system},
            {"role": "user", "content": user},
        ]
    )
    print(resp)
    return resp.choices[0].message.content

def extract_wikilinks(text:str)-> list[str]:
    """
    [[ + 一段不含 ] 的内容 + ]]
    :param text:
    :return:
    """
    return WIKILINK_RE.findall(text)

def write_page(rel:str,content:str)->Path:
    """
    创建rel路径，将content直接覆盖写入rel文件
    :param rel:
    :param content:
    :return:
    """
    path = WIKI_DIR/rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content,encoding="utf-8")
    return path

if __name__=="__main__":
    print(write_page("test/mddd","test_page"))