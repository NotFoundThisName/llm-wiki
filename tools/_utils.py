# 所有工具的唯一依赖：路径、LLM、哈希、wikilink
import hashlib
import os
import re
from pathlib import Path

# 代理软件常在 NO_PROXY 里塞 [::1]，httpx 会把它当成端口 ':1]' 报错。
# 必须在导入 litellm 之前清理：litellm 在 import 阶段就会发起网络请求。
os.environ["NO_PROXY"]=",".join(
    t for t in os.environ.get("NO_PROXY","").replace("[::1]","").split(",") if t
)

from litellm import completion

ROOT=Path(__file__).resolve().parent.parent
RAW_DIR,WIKI_DIR=ROOT/"raw",ROOT/"wiki"
INDEX,LOG=WIKI_DIR/"index.md",WIKI_DIR/"log.md"
SCHEMA_FILE=ROOT/"CLAUDE.md"
MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
WIKILINK_RE=re.compile(r"\[\[([^\]]+)\]\]")
# Windows 文件名非法字符：: 会变成 NTFS 数据流，? * " < > | 会直接报「文件名语法不正确」
INVALID_CHARS_RE=re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# index.md 的三个分区；query.py 靠 ](path.md) 正则扫描这里召回页面
INDEX_SECTIONS = (("sources", "## Sources"),
                  ("entities", "## Entities"),
                  ("concepts", "## Concepts"))

def safe_rel_path(rel:str)->str:
    """
    把 LLM 返回的页面路径规范成 WIKI_DIR 下的安全相对路径：
    - 统一分隔符，去掉模型重复带上的 wiki/ 前缀（否则会写成 wiki/wiki/...）
    - 拦截 .. 目录穿越
    - 替换 Windows 非法字符，去掉结尾的空格和点
    - 保证以 .md 结尾
    """
    parts=[p for p in str(rel).strip().replace("\\","/").split("/") if p not in ("",".")]
    if parts and parts[0].lower()=="wiki":
        parts=parts[1:]
    parts=[p for p in parts if p!=".."]
    cleaned=[]
    for p in parts:
        p=INVALID_CHARS_RE.sub("-",p).strip().rstrip(".")
        if p:
            cleaned.append(p)
    if not cleaned:
        cleaned=["untitled.md"]
    if not cleaned[-1].endswith(".md"):
        cleaned[-1]+=".md"
    return "/".join(cleaned)

def sha256(text:str)->str:
    """
    把字符串 text 按 UTF-8 编码后，计算它的 SHA-256 哈希值，并输出一个 十六进制字符串。
    :param text:
    :return:
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def call_llm(system:str,user:str,model:str = MODEL)->str:

    kw={}
    if model.startswith("deepseek"):
        # 显式传入 key，避免 litellm 内部环境变量查找不到而发出空 token（401 governor）
        api_key=os.getenv("DEEPSEEK_API_KEY","").strip()
        if not api_key:
            raise SystemExit("DEEPSEEK_API_KEY 为空：请先在当前终端设置它（export/setx），再运行。")
        kw["api_key"]=api_key
        kw["api_base"]=os.getenv("DEEPSEEK_API_BASE","https://api.deepseek.com")
        kw["response_format"]={"type":"json_object"}
    resp=completion(
        model=model,
        messages=[
            {"role":"system","content":system},
            {"role": "user", "content": user},
        ],
        **kw
    )
    # print(resp)
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
    把 content 覆盖写入 WIKI_DIR 下的安全路径。
    先经 safe_rel_path 规范化，再校验没有逃出 wiki 目录。
    """
    base=WIKI_DIR.resolve()
    path=(base/safe_rel_path(rel)).resolve()
    if path!=base and base not in path.parents:
        raise ValueError(f"拒绝写出 wiki 目录之外: {rel!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content,encoding="utf-8")
    return path

def append_index(entrties:list[tuple[str,str,str]])->None:
    # entries: [(分类, 标题, 相对路径), ...]，先解析旧内容再整体重写，天然去重
    sections={k:[] for k,_ in INDEX_SECTIONS}
    if INDEX.exists():
        current = None
        for line in INDEX.read_text(encoding="ytf-8").splitlines():
            if line.startswith("## "):
                current = line[3:].lower().strip()
            # m得到的类似于  - [Python](wiki/python.md)
            m = re.match(r"- \[(.+?)\]\(([^)]+\.md)\)", line)
            if m and current in sections:
                # 第一个捕获组 和 第二个捕获组
                # Python
                # wiki/python.md
                sections[current].append((m.group(1), m.group(2)))

    for key,title,rel in entrties:
        if (title,rel) not in sections.setdefault(key.lower(),[]):
            # 如果 sections 里已经有 "entity"，返回它的列表
            # 如果没有，创建 sections["entity"] = []，并返回这个空列表
            sections[key.lower()].append((title,rel))

    out=["# 索引",""]
    for key,heading in INDEX_SECTIONS:
        if sections.get(key):
            out.append(heading)
            out += [f"- [{t}]({r})" for t,r in sections[key]]
            out.append("")
    INDEX.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


if __name__=="__main__":
    print(write_page("test/mddd","test_page"))