"""
知识库种子脚本：把 agent-interview-hub（/tmp/hub_kb 或系统临时目录下的克隆）
精选文档复制进 backend/data/kb_seed/，并生成分类元数据 categories.json。

健壮性：不做精确文件名匹配，而是遍历目录 + 关键词分类，避免 Windows /
Unicode 归一化导致文件名不匹配的问题。

用法：
    python scripts/seed_kb.py [源目录]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "kb_seed"

# 通用知识目录里允许收录的关键词 → 分类
GENERAL_RULES = [
    (("Agent核心概念", "设计模式"), "Agent"),
    (("RAG", "GraphRAG"), "RAG"),
    (("MCP", "工具生态"), "MCP/工具"),
    (("Function Calling", "Tool Use"), "MCP/工具"),
    (("LangChain", "LangGraph"), "LangChain/LangGraph"),
    (("八股文",), "八股文"),
    (("技术知识点", "核心概念详解"), "八股文"),
    (("大模型推理", "推理优化"), "模型/推理"),
    (("微调",), "模型/推理"),
    (("Agent框架", "Agent安全", "Agentic Coding", "AI协作"), "Agent"),
    (("Context Engineering", "上下文工程"), "上下文工程"),
    (("系统设计",), "系统设计"),
    (("面经", "高频面试", "高频拷打", "面经索引", "面试攻略"), "面经"),
    (("进阶路线", "学习路线"), "学习路线"),
]

# 明确排除的通用知识文件名关键词（太泛/太大/非题库）
GENERAL_EXCLUDE = ("GitHub热门Agent资源",)

# 需要收录的公司目录
COMPANIES = [
    "字节跳动", "阿里巴巴", "腾讯", "百度", "美团", "华为",
    "小红书", "蚂蚁集团", "快手", "谷歌", "Anthropic", "OpenAI", "微软", "商汤科技",
]


def classify_general(fname: str) -> str | None:
    if any(k in fname for k in GENERAL_EXCLUDE):
        return None
    for keys, cat in GENERAL_RULES:
        if all(k in fname for k in keys):
            return cat
    return None


def _default_source() -> Path:
    candidates = [
        Path("/tmp/hub_kb"),
        Path.home() / "AppData/Local/Temp/hub_kb",
        Path("../../hub_kb"),
    ]
    for c in candidates:
        if (c / "通用知识").exists():
            return c
    return Path("/tmp/hub_kb")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_source()
    if not src.exists():
        print(f"[!] 源目录不存在: {src}")
        sys.exit(1)

    if SEED_DIR.exists():
        shutil.rmtree(SEED_DIR)
    SEED_DIR.mkdir(parents=True, exist_ok=True)

    copied: list[tuple[str, str]] = []

    def _add(f: Path, cat: str) -> None:
        # 分类名可能含 "/"（如 MCP/工具），做路径安全化
        safe_cat = cat.replace("/", "-")
        dest = SEED_DIR / f"{safe_cat}__{f.name}"
        shutil.copy2(f, dest)
        copied.append((dest.name, cat))

    # 通用知识
    gen_dir = src / "通用知识"
    if gen_dir.exists():
        for f in sorted(gen_dir.glob("*.md")):
            cat = classify_general(f.name)
            if cat:
                _add(f, cat)

    # 公司
    for comp in COMPANIES:
        comp_dir = src / comp
        if comp_dir.exists():
            for f in sorted(comp_dir.glob("*.md")):
                cat = f"{comp}面经" if ("面经" in f.name or "实录" in f.name) else f"{comp}岗位"
                _add(f, cat)

    # 学习路线图
    roadmap = src / "Agent工程师学习路线图.md"
    if roadmap.exists():
        _add(roadmap, "学习路线")

    if not copied:
        print("[!] 没有复制任何文档，请检查源目录")
        sys.exit(1)

    # 分类元数据
    categories = sorted({c for _, c in copied})
    with open(SEED_DIR / "categories.json", "w", encoding="utf-8") as fh:
        json.dump({"categories": categories}, fh, ensure_ascii=False, indent=2)

    total_bytes = sum((SEED_DIR / n).stat().st_size for n, _ in copied)
    print(f"[✓] 复制 {len(copied)} 篇文档，{total_bytes / 1024:.0f} KB")
    print(f"[✓] 分类数: {len(categories)}")
    for c in categories:
        n = sum(1 for _, cc in copied if cc == c)
        print(f"    - {c}: {n}")


if __name__ == "__main__":
    main()
