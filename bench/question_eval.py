"""M4 出题/追问质量评测（LLM-as-judge）。

测试维度：
  出题质量（ask_question）：
    1. topic_relevance    — 是否围绕预设主题
    2. difficulty_fit     — 是否匹配难度（初/中/高）
    3. clarity            — 是否口语化、清晰不模糊
    4. groundedness       — 是否引用了检索到的真实知识（不是凭空编）
    5. type_fit           — 是否符合题型（concept/code/scenario）
    6. answer_leak        — 不应直接揭示答案

  追问质量（ask_followup）：
    1. targeted           — 针对候选回答的遗漏点
    2. depth              — 是否深挖（不是换个角度重问）
    3. brevity            — 不超过 80 字
    4. natural            — 不重复原题、不机械追问

Judge 模型：主 = 服务端 deepseek-flash（思考模式已禁用，max_tokens=4096）
成本预估：50 条 × 2 call × ~600 token ≈ 60K token ≈ ¥0.06
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

OUT_JSON = Path(__file__).with_name("question_eval_result.json")
OUT_MD = Path(__file__).with_name("question_eval_result.md")

# ── 测试用例：每学科 × 难度的出题预设 ────────────────────────────────
# （topic, question_type, focus, difficulty, expected_keywords）
QUESTION_CASES = [
    # ── 计算机 ──
    ("Docker", "concept", "容器与镜像的区别", "easy",
     ["容器", "镜像", "实例"]),
    ("MySQL", "concept", "InnoDB B+ 树索引", "medium",
     ["B+树", "索引", "数据"]),
    ("Redis", "scenario", "缓存穿透", "medium",
     ["缓存穿透", "查询", "不存在"]),
    ("动态规划入门", "concept", "状态转移方程", "hard",
     ["状态", "转移", "子问题"]),
    ("MySQL", "code", "SQL 事务隔离级别", "hard",
     ["事务", "隔离级别", "脏读"]),

    # ── 测试 ──
    ("Mock 与 Stub", "concept", "Mock 与 Stub 区别", "easy",
     ["Mock", "Stub", "行为"]),
    ("性能测试方法", "scenario", "压测策略", "medium",
     ["并发", "响应", "TPS"]),

    # ── 产品 ──
    ("PRD 写作指南", "concept", "PRD 结构", "easy",
     ["PRD", "需求", "验收"]),
    ("MVP 设计", "concept", "MVP 原则", "medium",
     ["MVP", "最小", "假设"]),

    # ── 经济学 ──
    ("GDP 与国民经济", "concept", "GDP 核算方法", "easy",
     ["GDP", "生产", "收入"]),
    ("货币政策", "concept", "货币工具", "medium",
     ["利率", "准备金", "公开市场"]),

    # ── 法学 ──
    ("民法物权", "concept", "所有权内容", "easy",
     ["占有", "使用", "收益"]),
    ("合同法基础", "scenario", "合同成立要件", "medium",
     ["要约", "承诺", "合意"]),

    # ── 哲学 ──
    ("古希腊哲学", "concept", "苏格拉底方法", "easy",
     ["产婆术", "苏格拉底", "定义"]),
    ("逻辑学基础", "concept", "三段论", "medium",
     ["前提", "结论", "推理"]),

    # ── 英语 ──
    ("英语语法时态", "concept", "完成时态", "easy",
     ["完成", "过去", "现在"]),
    ("雅思写作评分", "concept", "TR 评分维度", "medium",
     ["任务", "回应", "扣题"]),

    # ── 工业设计 ──
    ("设计思维", "concept", "五步流程", "easy",
     ["移情", "定义", "原型"]),
    ("人机工程学", "concept", "座椅设计要点", "medium",
     ["座椅", "高度", "腰椎"]),
]

# ── 追问测试用例：原题 + 弱答 + 期望追问方向 ────────────────────────
FOLLOWUP_CASES = [
    {
        "orig_q": "请解释 Docker 容器与镜像的区别",
        "orig_a": "镜像就是容器，容器就是镜像",                # 完全答错
        "missing": ["镜像只读模板", "容器是运行实例"],
        "expect_keywords": ["区别", "模板", "实例", "运行时"],
    },
    {
        "orig_q": "什么是 InnoDB B+ 树索引？为什么不用红黑树？",
        "orig_a": "B+ 树是多叉树，磁盘友好",                  # 答得不完整
        "missing": ["叶子节点链表", "范围扫描", "IO 次数"],
        "expect_keywords": ["范围", "叶子", "扫描"],
    },
    {
        "orig_q": "Redis 缓存穿透怎么解决？",
        "orig_a": "加 Redis 缓存",                              # 完全偏题
        "missing": ["布隆过滤器", "空值缓存", "接口校验"],
        "expect_keywords": ["布隆", "空值", "校验"],
    },
    {
        "orig_q": "KANO 模型分几类需求？",
        "orig_a": "基本型和期望型",                             # 漏两类
        "missing": ["兴奋型", "无差异型", "反向型"],
        "expect_keywords": ["兴奋", "无差异", "反向"],
    },
    {
        "orig_q": "MVP 的设计原则是什么？",
        "orig_a": "快速开发",                                   # 太笼统
        "missing": ["最小可行", "假设验证", "迭代"],
        "expect_keywords": ["假设", "验证", "迭代"],
    },
    {
        "orig_q": "GDP 的三种核算方法？",
        "orig_a": "生产法",                                     # 只答一种
        "missing": ["收入法", "支出法", "恒等式"],
        "expect_keywords": ["收入", "支出", "恒等"],
    },
    {
        "orig_q": "苏格拉底方法的核心是什么？",
        "orig_a": "提问",                                       # 答得太浅
        "missing": ["产婆术", "反讽", "定义澄清"],
        "expect_keywords": ["产婆", "反讽", "定义"],
    },
    {
        "orig_q": "B+ 树索引为什么比红黑树快？",
        "orig_a": "因为 B+ 树是多叉的",                         # 没答到点
        "missing": ["磁盘 IO 次数", "扇区对齐", "范围扫描"],
        "expect_keywords": ["磁盘", "IO", "扇区"],
    },
]

# ── Judge prompt ────────────────────────────────────────────────────
JUDGE_PROMPT = """你是面试题质量评审员，严格按 0/1/2 三级打分（2=完全达标，1=部分达标，0=不达标）。
输出严格 JSON：{{"scores": {{"<维度>": <0/1/2>}}, "reason": "<一句话原因>"}}

评估对象：
- 主题: {topic}
- 题型: {qtype}
- 难度: {difficulty}
- 考察点: {focus}
- 检索到的参考资料: {context}
- 候选题目: {question}

评分维度（每个 0/1/2）：
- topic_relevance: 是否围绕考察点主题
- difficulty_fit:   是否匹配预设难度（easy=基础；medium=应用；hard=原理深度）
- clarity:         是否口语化、清晰、不模糊
- groundedness:    是否引用了参考资料中的真实概念/术语（不是凭空编造）
- type_fit:        是否符合题型（concept=概念解释；code=写代码；scenario=情境解决）
- answer_leak:     不应直接透露答案（2=无泄露；1=小提示但未直说；0=直接给答案）

注意：候选题目应 **像真实面试官提问**，不超过 120 字。
"""


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从 LLM 返回中抠 JSON（容忍代码围栏、多余文本、嵌套花括号）。

    关键修复：原实现用 `\{[\s\S]*\}` 贪婪匹配，遇到「提示词里含 {} 占位符」时会
    把占位符当外层 JSON、真正的 JSON 被吞掉。改为平衡花括号匹配 + 从「第一个
    看起来像 JSON 起点」开始。
    """
    if not text:
        return None
    # 去围栏
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    # 从每个可能的 JSON 起点尝试解析，返回第一个成功的
    starts = [i for i in range(len(text)) if text[i] == "{"]
    for s in starts[:20]:  # 防止病态输入
        # 平衡花括号扫描
        depth = 0
        for e in range(s, min(s + 4000, len(text))):
            if text[e] == "{":
                depth += 1
            elif text[e] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[s:e + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # 这个起点不是 JSON，往下找
    return None


async def judge_one(judge_llm, topic: str, qtype: str, difficulty: str,
                    focus: str, context: str, question: str) -> Dict[str, Any]:
    """单条评分。"""
    prompt = JUDGE_PROMPT.format(
        topic=topic, qtype=qtype, difficulty=difficulty, focus=focus,
        context=context[:800], question=question[:400])
    try:
        text = await judge_llm.chat(
            system_prompt="你是严格的质量评审员。",
            user_prompt=prompt, temperature=0.0, max_tokens=512)
        parsed = _extract_json(text or "")
        if parsed and "scores" in parsed:
            return {"scores": parsed["scores"], "reason": parsed.get("reason", "")[:100]}
        return {"scores": {}, "reason": f"parse_failed: {(text or '')[:80]}"}
    except Exception as e:  # noqa: BLE001
        return {"scores": {}, "reason": f"judge_error: {type(e).__name__}: {e}"[:120]}


# ── 出题评测 ───────────────────────────────────────────────────────
async def evaluate_questions(judge_llm, asker, retriever) -> List[Dict[str, Any]]:
    out = []
    for i, (topic, qtype, focus, diff, keywords) in enumerate(QUESTION_CASES, 1):
        # 用真实检索获取参考资料（groundedness 维度的依据）
        retrieved = await retriever(topic, top_k=3)
        context = "\n".join([f"- {r.get('text', '')[:150]}" for r in retrieved])
        # 出题
        preset = {"topic": topic, "question_type": qtype, "focus": focus,
                  "prompt": f"围绕 {focus}"}
        state = {
            "question_plan": [preset], "current_question_idx": 0,
            "qa_history": [], "score_records": [],
            "jd_parsed": {"level": "mid", "title": topic},
            "resume_parsed": {"summary": ""},
            "current_difficulty": diff,
        }
        try:
            question = await asker.ask_question(state)
        except Exception as e:  # noqa: BLE001
            out.append({"idx": i, "topic": topic, "qtype": qtype, "diff": diff,
                        "question": "", "keywords": keywords,
                        "judge": {"scores": {}, "reason": f"ask_error: {e}"}})
            print(f"[{i:>2}/{len(QUESTION_CASES)}] {topic}/{diff} → 出题失败: {e}")
            continue
        judge = await judge_one(judge_llm, topic, qtype, diff, focus, context, question)
        out.append({"idx": i, "topic": topic, "qtype": qtype, "diff": diff,
                    "question": question, "keywords": keywords, "judge": judge})
        s = judge.get("scores", {})
        avg = (sum(s.values()) / max(len(s), 1)) if s else 0
        print(f"[{i:>2}/{len(QUESTION_CASES)}] {topic}/{diff} avg={avg:.1f} → {question[:60]}")
    return out


# ── 追问评测 ───────────────────────────────────────────────────────
FOLLOWUP_JUDGE_PROMPT = """你是面试追问质量评审员。
原题: {orig_q}
候选回答: {orig_a}
回答遗漏点: {missing}
候选追问: {followup}

评分维度（0/1/2）：
- targeted: 是否针对原回答的遗漏点追问（不是原题重述）
- depth:     是否深挖，而非换个角度重问
- brevity:   不超过 80 字（2=短而精；1=略长；0=冗长）
- natural:   不机械、不重复原题

输出严格 JSON：{{"scores": {{"targeted": <0/1/2>, "depth": <0/1/2>, "brevity": <0/1/2>, "natural": <0/1/2>}}, "reason": "<一句话原因>"}}
"""


async def evaluate_followups(judge_llm, asker) -> List[Dict[str, Any]]:
    out = []
    for i, case in enumerate(FOLLOWUP_CASES, 1):
        state = {
            "qa_history": [{
                "question": case["orig_q"],
                "answer": case["orig_a"],
                "score": {"key_missing": case["missing"]},
            }],
            "score_records": [], "current_question_difficulty": "medium",
            "question_plan": [],
        }
        try:
            followup = await asker.ask_followup(state)
        except Exception as e:  # noqa: BLE001
            out.append({"idx": i, "orig_q": case["orig_q"], "followup": "",
                        "expect": case["expect_keywords"],
                        "judge": {"scores": {}, "reason": f"ask_error: {e}"}})
            continue
        prompt = FOLLOWUP_JUDGE_PROMPT.format(
            orig_q=case["orig_q"], orig_a=case["orig_a"][:200],
            missing="；".join(case["missing"]), followup=followup[:200])
        try:
            text = await judge_llm.chat(
                system_prompt="你是严格的追问质量评审员。",
                user_prompt=prompt, temperature=0.0, max_tokens=400)
            parsed = _extract_json(text or "")
            if parsed and "scores" in parsed:
                judge = {"scores": parsed["scores"], "reason": parsed.get("reason", "")[:100]}
            else:
                judge = {"scores": {}, "reason": f"parse_failed: {(text or '')[:80]}"}
        except Exception as e:  # noqa: BLE001
            judge = {"scores": {}, "reason": f"judge_error: {e}"}
        out.append({"idx": i, "orig_q": case["orig_q"], "followup": followup,
                    "expect": case["expect_keywords"], "judge": judge})
        s = judge.get("scores", {})
        avg = (sum(s.values()) / max(len(s), 1)) if s else 0
        print(f"[{i:>2}/{len(FOLLOWUP_CASES)}] avg={avg:.1f} → {followup[:60]}")
    return out


def aggregate(items: List[Dict[str, Any]], dims: List[str]) -> Dict[str, float]:
    """聚合各维度平均分。"""
    sums = {d: 0.0 for d in dims}
    counts = {d: 0 for d in dims}
    for it in items:
        s = it.get("judge", {}).get("scores", {})
        for d in dims:
            if d in s and isinstance(s[d], (int, float)):
                sums[d] += s[d]
                counts[d] += 1
    return {d: round(sums[d] / counts[d], 2) if counts[d] else 0.0
            for d in dims}


def render_md(qres: List[Dict[str, Any]], fres: List[Dict[str, Any]],
              agg_q: Dict[str, float], agg_f: Dict[str, float]) -> str:
    lines = [
        "# 出题/追问质量评测（LLM-as-judge）",
        "",
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"Judge 模型：DeepSeek（思考模式禁用，max_tokens=4096）",
        f"出题样本：{len(qres)} 条；追问样本：{len(fres)} 条",
        "",
        "## 出题质量各维度平均分（满分 2.0）",
        "",
        "| 维度 | 平均分 | 解读 |",
        "|---|---|---|",
    ]
    desc = {
        "topic_relevance": "是否围绕主题",
        "difficulty_fit":   "难度匹配",
        "clarity":         "清晰度",
        "groundedness":    "是否引用真实知识",
        "type_fit":        "题型匹配",
        "answer_leak":     "无答案泄露",
    }
    for d, sc in agg_q.items():
        lines.append(f"| {d} | {sc:.2f} | {desc.get(d, '')} |")
    overall = round(sum(agg_q.values()) / max(len(agg_q), 1), 2)
    lines.append(f"\n**出题总评：{overall} / 2.0**\n")

    lines += [
        "## 追问质量各维度平均分（满分 2.0）",
        "",
        "| 维度 | 平均分 | 解读 |",
        "|---|---|---|",
    ]
    desc_f = {
        "targeted": "针对遗漏点",
        "depth":    "是否深挖",
        "brevity":  "简洁性",
        "natural":  "自然度",
    }
    for d, sc in agg_f.items():
        lines.append(f"| {d} | {sc:.2f} | {desc_f.get(d, '')} |")
    overall_f = round(sum(agg_f.values()) / max(len(agg_f), 1), 2)
    lines.append(f"\n**追问总评：{overall_f} / 2.0**\n")

    # 失败样本
    lines += ["## 失败样本（judge 报错或解析失败）", ""]
    fails = [it for it in qres + fres if not it.get("judge", {}).get("scores")]
    if not fails:
        lines.append("（无）")
    else:
        for it in fails[:10]:
            r = it.get("judge", {}).get("reason", "")
            lines.append(f"- [{it.get('idx')}] {it.get('topic', it.get('orig_q', ''))[:40]}：{r}")

    # 亮点样本
    lines += ["", "## 高分样本摘录", ""]
    for it in qres[:3]:
        s = it.get("judge", {}).get("scores", {})
        avg = sum(s.values()) / max(len(s), 1) if s else 0
        lines.append(f"- **{it['topic']}**（{it['diff']}，avg={avg:.2f}）：{it['question']}")
    lines.append("")
    for it in fres[:3]:
        s = it.get("judge", {}).get("scores", {})
        avg = sum(s.values()) / max(len(s), 1) if s else 0
        lines.append(f"- **追问**（avg={avg:.2f}）：{it['followup']}")
    return "\n".join(lines) + "\n"


async def main() -> None:
    from app.agents.interviewer import interviewer
    from app.config import settings
    from app.llm import llm_client
    from app.observability import init_budget, new_meter
    from app.rag.engine import query_engine

    settings.llm_thinking_mode = "disabled"  # 关键：避免静默空回答
    settings.llm_max_tokens = 4096
    init_budget()
    new_meter()

    print(f"Judge 模型: {settings.llm_model}")
    print(f"评测规模: 出题 {len(QUESTION_CASES)} / 追问 {len(FOLLOWUP_CASES)}")

    # 简化版的检索（直接用 query_engine.full_query）
    async def retriever(q: str, top_k: int = 3):
        try:
            results = await query_engine.full_query(q, top_k=top_k, use_rerank=False)
            return [{"text": (r.get("text") or r.get("content") or "")} for r in results]
        except Exception:
            # mock 回退：用于无 API key / 索引失败场景
            return [{"text": f"参考资料{i}：关于{q}的基础知识示例。"} for i in range(top_k)]

    qres = await evaluate_questions(llm_client, interviewer, retriever)
    fres = await evaluate_followups(llm_client, interviewer)

    agg_q = aggregate(qres, ["topic_relevance", "difficulty_fit", "clarity",
                              "groundedness", "type_fit", "answer_leak"])
    agg_f = aggregate(fres, ["targeted", "depth", "brevity", "natural"])

    OUT_JSON.write_text(json.dumps({
        "questions": qres, "followups": fres,
        "agg_questions": agg_q, "agg_followups": agg_f,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_MD.write_text(render_md(qres, fres, agg_q, agg_f), encoding="utf-8")
    print(f"\n报告 → {OUT_MD.name}")
    print(f"原始数据 → {OUT_JSON.name}")


if __name__ == "__main__":
    asyncio.run(main())
