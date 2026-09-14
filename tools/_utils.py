# tools/_utils.py
# 所有工具（ingest / query / health ...）共用的唯一底座。
# 只负责四件事：路径常量、LLM 调用、内容哈希、wikilink 解析，
# 以及写页面 / 更新索引 / 写日志这几个落盘动作。
# 依赖方向是单向的：所有工具 → _utils，_utils 不反向依赖任何工具。

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

# --- 环境自愈：必须放在导入 litellm 之前 ---
# 代理软件（Clash 等）常在 NO_PROXY 里塞 "[::1]"，httpx 解析时会把它当成端口，
# 抛出 "Invalid port: ':1]'"。litellm 在 import 阶段就可能发起网络请求，
# 所以要在 import 之前先把 NO_PROXY 里的 "[::1]" 去掉，并丢掉空项避免出现多余逗号。
os.environ["NO_PROXY"] = ",".join(
    t for t in os.environ.get("NO_PROXY", "").replace("[::1]", "").split(",") if t
)

from litellm import completion

# --- 路径常量：整个项目以「仓库根目录」为基准，所有路径都由它派生 ---
ROOT = Path(__file__).resolve().parent.parent      # _utils.py 在 tools/ 下，再往上一层就是仓库根
RAW_DIR, WIKI_DIR = ROOT / "raw", ROOT / "wiki"    # raw=不可变源文档；wiki=生成的的知识层
INDEX, LOG = WIKI_DIR / "index.md", WIKI_DIR / "log.md"
SCHEMA_FILE = ROOT / "CLAUDE.md"                   # Schema（页面格式与工作流定义）
MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")  # 默认模型，可用环境变量覆盖

# 匹配 [[wikilink]]，捕获中间不含 ] 的内容
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# Windows 文件名非法字符：: 会变成 NTFS 数据流，? * " < > | 会直接报「文件名语法不正确」
INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# index.md 的三个分区；query.py 靠 ](path.md) 正则扫描这里召回页面
INDEX_SECTIONS = (("sources", "## Sources"),
                  ("entities", "## Entities"),
                  ("concepts", "## Concepts"))


def safe_rel_path(rel: str) -> str:
    """
    把 LLM 返回的页面路径规范成 WIKI_DIR 下的安全相对路径：
    - 统一分隔符，去掉模型重复带上的 wiki/ 前缀（否则会写成 wiki/wiki/...）
    - 拦截 .. 目录穿越
    - 替换 Windows 非法字符，去掉结尾的空格和点
    - 保证以 .md 结尾
    """
    # 统一成 / 分隔，丢掉空段和 "." 段
    parts = [p for p in str(rel).strip().replace("\\", "/").split("/") if p not in ("", ".")]
    # 模型常把路径写成 "wiki/sources/x.md"，这里剥掉开头的 wiki，避免嵌套
    if parts and parts[0].lower() == "wiki":
        parts = parts[1:]
    # 过滤掉 ".." 段，防止写文件时穿越到 wiki 之外
    parts = [p for p in parts if p != ".."]
    cleaned = []
    for p in parts:
        # 非法字符换成 "-"，再去掉结尾的空格和点（Windows 不允许）
        p = INVALID_CHARS_RE.sub("-", p).strip().rstrip(".")
        if p:
            cleaned.append(p)
    if not cleaned:
        cleaned = ["untitled.md"]              # 全被清空时给个兜底文件名
    if not cleaned[-1].endswith(".md"):
        cleaned[-1] += ".md"                   # 保证是 Markdown 文件
    return "/".join(cleaned)


def sha256(text: str) -> str:
    """
    把字符串按 UTF-8 编码后计算 SHA-256，返回十六进制字符串。
    用于内容去重 / 增量判断：内容没变则哈希相同。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_llm(system: str, user: str, model: str = MODEL) -> str:
    """
    调用 LLM（经 litellm 统一入口），返回首条回复的文本内容。
    - system：系统提示，负责设定角色与输出约束
    - user：用户内容，通常塞入 schema + 索引 + 源文档
    - model：模型名，默认取环境变量 LLM_MODEL
    """
    kw = {}
    # DeepSeek 需要一些特殊处理：
    if model.startswith("deepseek"):
        # 显式传入 key，避免 litellm 内部环境变量查找不到而发出空 token（401 governor）
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise SystemExit("DEEPSEEK_API_KEY 为空：请先在当前终端设置它（export/setx），再运行。")
        kw["api_key"] = api_key
        # 固定 api_base，保证打到你验证过的 /chat/completions 端点
        kw["api_base"] = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        # 强制返回 JSON，配合 ingest 的结构化解析
        kw["response_format"] = {"type": "json_object"}
    resp = completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kw
    )
    # print(resp)  # 调试用：会打印整个 Response 对象，平时关掉
    return resp.choices[0].message.content


def extract_wikilinks(text: str) -> list[str]:
    """
    从文本中提取所有 [[wikilink]] 的内部名称，返回名称列表。
    匹配规则：[[ + 一段不含 ] 的内容 + ]]
    """
    return WIKILINK_RE.findall(text)


def write_page(rel: str, content: str) -> Path:
    """
    把 content 覆盖写入 WIKI_DIR 下的安全路径，返回写入后的绝对路径。
    先经 safe_rel_path 规范化，再校验没有逃出 wiki 目录。
    """
    base = WIKI_DIR.resolve()
    path = (base / safe_rel_path(rel)).resolve()
    # 安全校验：解析后的路径必须仍在 wiki 目录内，否则拒绝写入
    if path != base and base not in path.parents:
        raise ValueError(f"拒绝写出 wiki 目录之外: {rel!r}")
    path.parent.mkdir(parents=True, exist_ok=True)   # 自动创建缺失的父目录
    path.write_text(content, encoding="utf-8")
    return path


def append_index(entrties: list[tuple[str, str, str]]) -> None:
    """
    更新 wiki/index.md：把新页面条目合并进对应分区。
    entries 形如 [(分类, 标题, 相对路径), ...]，分类取 sources/entities/concepts。
    做法是「先解析旧内容 → 合并去重 → 整体重写」，因此天然幂等、可重复调用。
    """
    # 先按分区建空桶，例如 {"sources": [], "entities": [], "concepts": []}
    sections = {k: [] for k, _ in INDEX_SECTIONS}
    # 解析已有 index：逐行识别 "## 分区" 与 "- [标题](路径.md)" 条目
    if INDEX.exists():
        current = None
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                current = line[3:].lower().strip()          # 当前所属分区名
            # 匹配形如  - [Python](wiki/python.md)
            m = re.match(r"- \[(.+?)\]\(([^)]+\.md)\)", line)
            if m and current in sections:
                # 第一个捕获组是标题，第二个是路径
                # Python
                # wiki/python.md
                sections[current].append((m.group(1), m.group(2)))

    # 合并新条目：按 (标题, 路径) 去重，避免重复写入同一页
    for key, title, rel in entrties:
        if (title, rel) not in sections.setdefault(key.lower(), []):
            # setdefault：有 "entities" 就返回它的列表，没有就创建空列表再返回
            sections[key.lower()].append((title, rel))

    # 按固定分区顺序重写整个 index.md，保证输出稳定、可对比
    out = ["# 索引", ""]
    for key, heading in INDEX_SECTIONS:
        if sections.get(key):
            out.append(heading)
            out += [f"- [{t}]({r})" for t, r in sections[key]]
            out.append("")
    INDEX.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def append_log(entry: str) -> None:
    '''
    把最新条目前插到 log.md（最新在最上面），格式：

    ## 2026-09-14 15:30
    <entry 内容>

    :param entry: 最新的日志条目
    :return:
    '''
    # 读取旧内容并去掉首尾空白；文件不存在则视为空
    prev = LOG.read_text(encoding="utf-8").strip() if LOG.exists() else ""
    # 用当前时间生成新条目块，如 "## 2026-09-14 15:30\n<entry>"
    block = f"## {datetime.now():%Y-%m-%d %H:%M}\n{entry}"
    if not prev:
        # 首次写日志：补上一级标题
        LOG.write_text(f"# 日志\n\n{block}\n", encoding="utf-8")
    elif prev.startswith("# "):
        # 已有 "# 日志" 标题：保留标题在第一行，新条目插在它下面
        head, _, rest = prev.partition("\n")
        LOG.write_text(f"{head}\n\n{block}\n\n{rest.lstrip()}\n", encoding="utf-8")
    else:
        # 没有标题：直接把新条目放在最前面
        LOG.write_text(f"{block}\n\n{prev}\n", encoding="utf-8")


if __name__ == "__main__":
    # 遗留的自测代码，保持注释，避免误写垃圾文件到 wiki/
    # print(write_page("test/mddd", "test_page"))
    pass
