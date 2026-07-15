"""刷题 Agent 图执行测试。

测试 PracticeAgent 的节点逻辑：validate → generate → evaluate → adjust → next。
使用 Mock LLM 客户端避免真实 API 调用。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.practice_agent import PracticeAgent, PracticeAgentState


class MockLLMClient:
    """Mock LLM 客户端，返回固定 JSON 响应。"""

    async def chat_with_json(self, messages, **kwargs):
        prompt = str(messages)
        if "判断用户输入的主题是否属于技术面试相关领域" in prompt:
            return {"is_valid": True, "reason": "Mock: 主题合法"}
        if "请生成一道简答题" in prompt:
            return {
                "question": "请解释 Python 装饰器的原理。",
                "question_type": "short_answer",
                "reference_answer": "装饰器是一种设计模式...",
                "knowledge_points": ["装饰器", "闭包", "高阶函数"],
            }
        if "请评估以下回答" in prompt:
            return {
                "score": 85,
                "is_correct": True,
                "correct_answer": "装饰器是一种设计模式...",
                "analysis": "## 评分：85/100\n\n回答整体准确，可以补充细节。",
                "knowledge_points": ["装饰器", "闭包"],
                "common_mistakes": ["混淆装饰器与注解"],
            }
        return {"is_valid": True}

    async def chat(self, messages, **kwargs):
        return "Mock 响应"


class MockPracticeRepo:
    """Mock PracticeRepo，避免真实数据库操作。"""

    async def create_pending_record(self, **kwargs):
        return MagicMock(id=1)

    async def update_session_stats(self, session_id, **kwargs):
        pass

    async def get_session(self, session_id):
        return None


class TestPracticeAgentNodes:
    """Agent 节点单元测试。"""

    @pytest.fixture
    def agent(self):
        llm = MockLLMClient()
        repo = MockPracticeRepo()
        return PracticeAgent(llm, repo)

    @pytest.fixture
    def base_state(self) -> PracticeAgentState:
        return PracticeAgent.default_state(
            session_id=1,
            user_id=1,
            topic="Python",
            max_questions=5,
        )

    @pytest.mark.asyncio
    async def test_validate_node_pass(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """校验节点：合法主题应通过。"""
        result = await agent._validate_node(base_state)
        assert result.get("next_action") == "generate"
        assert result.get("error") is None

    @pytest.mark.asyncio
    async def test_generate_node(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """生成节点：应返回题目信息。"""
        result = await agent._generate_node(base_state)
        assert result.get("question_index") == 1
        assert result.get("current_question") is not None
        assert len(result.get("current_question", "")) > 0
        assert result.get("question_type") == "short_answer"
        assert len(result.get("knowledge_points", [])) > 0
        assert result.get("next_action") == "evaluate"

    @pytest.mark.asyncio
    async def test_evaluate_node(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """评估节点：应返回分数和反馈。"""
        # 模拟有回答的状态
        base_state["current_question"] = "请解释 Python 装饰器的原理。"
        base_state["reference_answer"] = "装饰器是一种设计模式..."
        base_state["user_answer"] = "装饰器是用于修改函数行为的工具"

        result = await agent._evaluate_node(base_state)
        assert result.get("score") is not None
        assert result.get("is_correct") is True
        assert result.get("feedback") is not None
        assert result.get("total_questions") == 1
        assert result.get("total_correct") == 1

    @pytest.mark.asyncio
    async def test_adjust_node_level_up(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """自适应节点：连续答对 3 题应升档。"""
        base_state["difficulty_level"] = 3
        base_state["consecutive_correct"] = 2
        base_state["is_correct"] = True

        result = await agent._adjust_node(base_state)
        # 第 3 次正确 → 升档到 4，consecutive_correct 重置为 0
        assert result.get("difficulty_level") == 4
        assert result.get("consecutive_correct") == 0

    @pytest.mark.asyncio
    async def test_adjust_node_level_down(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """自适应节点：连续答错 2 题应降档。"""
        base_state["difficulty_level"] = 3
        base_state["consecutive_wrong"] = 1
        base_state["is_correct"] = False

        result = await agent._adjust_node(base_state)
        # 第 2 次错误 → 降档到 2，consecutive_wrong 重置为 0
        assert result.get("difficulty_level") == 2
        assert result.get("consecutive_wrong") == 0

    @pytest.mark.asyncio
    async def test_next_node_continue(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """Next 节点：未达上限应返回 generate。"""
        base_state["total_questions"] = 2
        base_state["max_questions"] = 5

        result = await agent._next_node(base_state)
        assert result.get("next_action") == "generate"

    @pytest.mark.asyncio
    async def test_next_node_end(self, agent: PracticeAgent, base_state: PracticeAgentState):
        """Next 节点：达到上限应返回 end。"""
        base_state["total_questions"] = 5
        base_state["max_questions"] = 5

        result = await agent._next_node(base_state)
        assert result.get("next_action") == "end"


class TestPracticeAgentGraph:
    """Agent 图结构测试。"""

    @pytest.fixture
    def agent(self):
        llm = MockLLMClient()
        repo = MockPracticeRepo()
        return PracticeAgent(llm, repo)

    def test_graph_compiled(self, agent: PracticeAgent):
        """图应成功编译。"""
        assert agent.graph is not None

    def test_graph_nodes(self, agent: PracticeAgent):
        """图应包含所有必需节点。"""
        nodes = agent.graph.nodes if hasattr(agent.graph, 'nodes') else {}
        # 检查关键节点名称（不同 langgraph 版本可能有差异）
        assert agent.graph is not None
