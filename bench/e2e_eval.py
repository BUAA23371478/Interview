"""M5 端到端冒烟：练习 + 模拟面试两条路径（适配各 Agent 实际接口）。

不走真实 HTTP，直接调用各 Agent 的对应方法，覆盖核心流程：
JD 解析 → 简历解析 → 出题规划 → 出题 → 答 → 评分 → 追问 → 报告。

约束：
- test_mode=True（无 key 时走 mock，0 外部调用）
- 真实 key 时记录 token 花费
- 检查点：每步耗时 / 是否成功 / 关键字段存在
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

OUT_JSON = Path(__file__).with_name("e2e_eval_result.json")
OUT_MD = Path(__file__).with_name("e2e_eval_result.md")


def _init_state(mode: str) -> Dict[str, Any]:
    return {
        "mode": mode,
        "jd_parsed": {
            "title": "高级 Python 后端工程师",
            "company": "某互联网公司",
            "level": "senior",
            "responsibilities": ["负责高并发后端服务开发", "设计 DB schema", "代码 review"],
            "required_skills": ["Python", "FastAPI", "MySQL", "Redis", "Docker"],
        },
        "resume_parsed": {
            "name": "张三", "years": 5,
            "skills": ["Python", "Django", "PostgreSQL", "Docker"],
            "summary": "5 年 Python 后端经验，主导过 3 个高并发服务",
        },
        "qa_history": [], "score_records": [],
        "current_question_idx": 0, "current_difficulty": "medium",
    }


async def _timed(coro, log: List[Dict[str, Any]], name: str) -> Any:
    """记时并捕获异常。"""
    t0 = time.perf_counter()
    try:
        r = await coro
        log.append({"name": name, "ok": True,
                    "ms": round((time.perf_counter() - t0) * 1000, 1),
                    "err": ""})
        return r
    except Exception as e:  # noqa: BLE001
        log.append({"name": name, "ok": False,
                    "ms": round((time.perf_counter() - t0) * 1000, 1),
                    "err": f"{type(e).__name__}: {e}"[:120]})
        return None


async def run_practice_mode() -> Dict[str, Any]:
    """练习模式：完整单题流程。"""
    from app.agents.evaluator import evaluator
    from app.agents.interviewer import interviewer
    from app.agents.jd_analyzer import jd_analyzer
    from app.agents.question_planner import question_planner
    from app.agents.resume_analyzer import resume_analyzer
    from app.agents.study_planner import study_planner

    log: List[Dict[str, Any]] = []
    state = _init_state("practice")

    await _timed(jd_analyzer.run(state), log, "jd_parse")
    await _timed(resume_analyzer.run(state), log, "resume_parse")
    await _timed(question_planner.run(state), log, "question_plan")

    # 出题（interviewer 用自己的方法，不写入 state）
    q1 = await _timed(interviewer.ask_question(state), log, "ask_question_1")
    if q1:
        state["qa_history"].append({"question": q1})  # 手动维护
        log.append({"name": "submit_answer_1", "ok": True, "ms": 0.0, "err": "（模拟用户答）"})
        state["qa_history"][-1]["answer"] = "镜像相当于类，容器相当于实例。镜像只读，容器在镜像之上加可写层。"
        # 评分
        sc = await _timed(evaluator.score_one(
            question=state["qa_history"][-1]["question"],
            answer=state["qa_history"][-1]["answer"]), log, "score_question_1")
        if sc:
            state["qa_history"][-1]["score"] = sc
            state["score_records"].append({"score": sc})
        # 追问（仅在有遗漏时）
        if sc and sc.get("key_missing"):
            fu = await _timed(interviewer.ask_followup(state), log, "followup_question")
            if fu:
                state["qa_history"].append({"question": fu, "answer": "（模拟）"})
        else:
            log.append({"name": "followup_question", "ok": True, "ms": 0.0,
                        "err": "无遗漏，跳过"})

    # 收尾
    await _timed(interviewer.farewell(state), log, "complete_session")
    # 学习计划（报告生成）
    await _timed(study_planner.run(state), log, "report_generation")

    return {"mode": "practice", "log": log,
            "n_questions": len(state.get("qa_history", [])),
            "farewell": state.get("farewell", "")[:80]}


async def run_mock_interview() -> Dict[str, Any]:
    """模拟面试：3 题自动推进。"""
    from app.agents.evaluator import evaluator
    from app.agents.interviewer import interviewer

    log: List[Dict[str, Any]] = []
    state = _init_state("mock_interview")
    state["question_plan"] = [
        {"topic": "Docker", "question_type": "concept", "focus": "容器与镜像", "prompt": ""},
        {"topic": "MySQL", "question_type": "concept", "focus": "事务隔离", "prompt": ""},
        {"topic": "Redis", "question_type": "scenario", "focus": "缓存穿透", "prompt": ""},
    ]

    for i, q in enumerate(state["question_plan"], 1):
        state["current_question_idx"] = i - 1
        q_text = await _timed(interviewer.ask_question(state), log, f"ask_q{i}")
        if q_text:
            state["qa_history"].append({"question": q_text})
            state["qa_history"][-1]["answer"] = f"模拟答案 {i}：关于{q['focus']}我的理解是……"
            sc = await _timed(evaluator.score_one(
                question=state["qa_history"][-1]["question"],
                answer=state["qa_history"][-1]["answer"]), log, f"score_q{i}")
            if sc:
                state["qa_history"][-1]["score"] = sc
                state["score_records"].append({"score": sc})

    await _timed(interviewer.farewell(state), log, "complete_session")
    return {"mode": "mock_interview", "log": log,
            "n_questions": len(state.get("qa_history", [])),
            "farewell": state.get("farewell", "")[:80]}


def render_md(results: Dict[str, Any]) -> str:
    lines = ["# 端到端冒烟（练习 + 模拟面试）", "",
             f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for mode in ("practice", "mock_interview"):
        r = results.get(mode, {})
        if not r:
            continue
        lines += [f"## {mode} 模式",
                  f"完成题数：{r.get('n_questions', 0)}", "",
                  "| 检查点 | 状态 | 耗时 | 备注 |",
                  "|---|---|---|---|"]
        for e in r.get("log", []):
            status = "✓" if e.get("ok") else "✗"
            lines.append(f"| {e['name']} | {status} | {e['ms']}ms | {e.get('err', '')[:60]} |")
        total = sum(e["ms"] for e in r.get("log", []))
        n_ok = sum(1 for e in r.get("log", []) if e.get("ok"))
        n_total = len(r.get("log", []))
        lines += ["",
                  f"**汇总**：{n_ok}/{n_total} 通过，总耗时 {total:.0f}ms", ""]
        if r.get("farewell"):
            lines += [f"收尾语示例：{r['farewell']}", ""]
    spend = results.get("spend", {})
    if spend:
        lines += ["## 成本流水",
                  f"已用：¥{spend.get('spent_yuan', 0):.4f} / 上限 ¥{spend.get('cap_yuan', 0)}",
                  f"调用次数：{sum(m.get('calls', 0) for m in spend.get('by_model', {}).values())}", ""]
    return "\n".join(lines) + "\n"


async def main() -> None:
    from app.config import settings
    from app.observability import init_budget, new_meter, spend_ledger

    settings.test_mode = True   # 走 mock，0 外部调用
    settings.llm_thinking_mode = "disabled"
    init_budget()
    new_meter()

    print("=== 练习模式 ===")
    practice = await run_practice_mode()
    print("\n=== 模拟面试模式 ===")
    mock = await run_mock_interview()

    results = {"practice": practice, "mock_interview": mock,
               "spend": spend_ledger.snapshot()}
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_MD.write_text(render_md(results), encoding="utf-8")
    print(f"\n报告 → {OUT_MD.name}")


if __name__ == "__main__":
    asyncio.run(main())
