"""LLM 结构化输出 Schema 定义。

集中管理所有 LLM 调用的 JSON Schema，供 LangGraph 节点或
UnifiedLLMClient.chat_with_json 参考使用。
"""

from __future__ import annotations

from typing import Any

# ---------- 主题校验 ----------
TOPIC_VALIDATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_valid": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["is_valid", "reason"],
}

# ---------- 刷题题目生成 ----------
PRACTICE_QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "question_type": {"type": "string", "enum": ["short_answer", "choice"]},
        "reference_answer": {"type": "string"},
        "knowledge_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question", "question_type", "reference_answer", "knowledge_points"],
}

# ---------- 面试题目生成 ----------
INTERVIEW_QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "knowledge_point": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
    },
    "required": ["question", "knowledge_point", "difficulty"],
}

# ---------- 评分/评估 ----------
EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "is_correct": {"type": "boolean"},
        "feedback": {"type": "string"},
    },
    "required": ["score", "is_correct", "feedback"],
}

# ---------- 面试下一步决策 ----------
INTERVIEW_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "should_follow_up": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["should_follow_up", "reason"],
}

# ---------- 面试复盘报告 ----------
INTERVIEW_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "tech_depth": {"type": "integer", "minimum": 0, "maximum": 100},
        "clarity": {"type": "integer", "minimum": 0, "maximum": 100},
        "logic": {"type": "integer", "minimum": 0, "maximum": 100},
        "job_match": {"type": "integer", "minimum": 0, "maximum": 100},
        "overall_comment": {"type": "string"},
        "round_reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "round": {"type": "integer"},
                    "question": {"type": "string"},
                    "answer_summary": {"type": "string"},
                    "comment": {"type": "string"},
                },
            },
        },
        "highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "round": {"type": "integer"},
                    "reason": {"type": "string"},
                },
            },
        },
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "overall_score",
        "tech_depth",
        "clarity",
        "logic",
        "job_match",
        "overall_comment",
    ],
}
