"""
Tests for SwarmDev v2 — multi-stack support.
Run with: pytest tests/ -v
"""
import asyncio
import os
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from swarm.config import SwarmConfig, detect_stack, get_roles_for_stack
from swarm.task_graph import TaskGraph, Task, TaskStatus, TaskPriority
from swarm.agents import Agent, AgentPool, AgentState
from swarm.memory import StigmergyMemory
from swarm.scaffolder import ProjectScaffolder
from swarm.verifier import Verifier


# ── Config tests ──────────────────────────────────────────────────────────────
class TestConfig:
    def test_default_config(self):
        cfg = SwarmConfig()
        assert cfg.total_agents == 1000
        assert cfg.agents_per_task == 10
        assert cfg.llm_provider == "groq"

    def test_detect_react(self):
        assert detect_stack("build a React app with Tailwind") == "react"

    def test_detect_fullstack(self):
        assert detect_stack("React frontend with FastAPI backend and database") == "fullstack"

    def test_detect_ml(self):
        assert detect_stack("train a PyTorch neural network model") == "ml"

    def test_detect_python(self):
        assert detect_stack("write a Python CLI tool with click") == "python"

    def test_detect_fallback(self):
        assert detect_stack("do something") == "python"

    def test_roles_for_react(self):
        roles = get_roles_for_stack("react")
        assert "frontend_dev" in roles
        assert "ui_designer" in roles

    def test_roles_for_fullstack(self):
        roles = get_roles_for_stack("fullstack")
        assert "backend_dev" in roles
        assert "frontend_dev" in roles
        assert "db_engineer" in roles

    def test_roles_for_ml(self):
        roles = get_roles_for_stack("ml")
        assert "ml_engineer" in roles
        assert "data_engineer" in roles


# ── Task graph tests ──────────────────────────────────────────────────────────
class TestTaskGraph:
    def _mock_llm(self, response: str):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=response)
        return llm

    @pytest.mark.asyncio
    async def test_build_with_valid_json(self):
        import json
        tasks_json = json.dumps([
            {"name": "Setup", "description": "scaffold", "skill": "scaffolding",
             "role": "architect", "priority": 1, "dependencies": []},
            {"name": "Components", "description": "build UI", "skill": "components",
             "role": "frontend_dev", "priority": 2, "dependencies": ["Setup"]},
        ])
        graph = TaskGraph(self._mock_llm(tasks_json), stack="react")
        tasks = await graph.build("cat food app", "test_proj")
        assert len(tasks) == 2
        assert tasks[0].skill == "scaffolding"
        assert tasks[1].skill == "components"

    @pytest.mark.asyncio
    async def test_fallback_on_bad_json(self):
        graph = TaskGraph(self._mock_llm("not json at all !!"), stack="python")
        tasks = await graph.build("build something", "proj")
        assert len(tasks) >= 2  # fallback tasks

    def test_ready_tasks(self):
        graph = TaskGraph(MagicMock(), stack="python")
        t1 = Task("t1", "A", "desc", "api", "backend_dev", dependencies=[])
        t2 = Task("t2", "B", "desc", "testing", "qa_engineer", dependencies=["t1"])
        graph.tasks = {"t1": t1, "t2": t2}
        ready = graph.ready_tasks(set())
        assert len(ready) == 1
        assert ready[0].id == "t1"
        ready2 = graph.ready_tasks({"t1"})
        assert ready2[0].id == "t2"

    def test_all_done(self):
        graph = TaskGraph(MagicMock(), stack="python")
        t1 = Task("t1", "A", "desc", "api", "backend_dev")
        t1.status = TaskStatus.DONE
        graph.tasks = {"t1": t1}
        assert graph.all_done()

    def test_not_all_done(self):
        graph = TaskGraph(MagicMock(), stack="python")
        t1 = Task("t1", "A", "desc", "api", "backend_dev")
        t1.status = TaskStatus.PENDING
        graph.tasks = {"t1": t1}
        assert not graph.all_done()


# ── Agent tests ───────────────────────────────────────────────────────────────
class TestAgent:
    def _make_agent(self, role="backend_dev", stack="python"):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value="# generated code\ndef hello(): pass")
        memory = MagicMock()
        memory.deposit = AsyncMock()
        memory.search = AsyncMock(return_value=[])
        a = Agent(role=role, stack=stack)
        a.inject(llm, memory)
        return a

    @pytest.mark.asyncio
    async def test_agent_work_creates_file(self, tmp_path):
        agent = self._make_agent()
        task = Task("t1", "Main API", "build main.py", "api", "backend_dev")
        result = await agent.work(task, str(tmp_path))
        assert result["success"]
        assert Path(result["file"]).exists()

    @pytest.mark.asyncio
    async def test_react_agent_creates_jsx(self, tmp_path):
        agent = self._make_agent(role="frontend_dev", stack="react")
        task = Task("t1", "Product Card", "React component", "components", "frontend_dev")
        result = await agent.work(task, str(tmp_path))
        assert result["success"]
        assert result["file"].endswith(".jsx")

    def test_agent_initial_state(self):
        a = Agent()
        assert a.state == AgentState.IDLE
        assert a.tasks_completed == 0

    def test_agent_pool_size(self):
        llm = MagicMock()
        memory = MagicMock()
        pool = AgentPool(total=100, stack="fullstack", llm=llm, memory=memory)
        assert len(pool.agents) > 0
        assert pool.idle_count() == len(pool.agents)


# ── Memory tests ──────────────────────────────────────────────────────────────
class TestMemory:
    @pytest.mark.asyncio
    async def test_deposit_and_retrieve(self):
        mem = StigmergyMemory(use_chroma=False)
        await mem.deposit("test_key", {"data": 42}, agent_id="agent_1")
        result = await mem.retrieve("test_key")
        assert result == {"data": 42}

    @pytest.mark.asyncio
    async def test_retrieve_missing_returns_none(self):
        mem = StigmergyMemory(use_chroma=False)
        result = await mem.retrieve("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_finds_match(self):
        mem = StigmergyMemory(use_chroma=False)
        await mem.deposit("react_component", "Button component code", agent_id="a1")
        results = await mem.search("react")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_decay(self):
        mem = StigmergyMemory(use_chroma=False)
        await mem.deposit("old_key", "value", strength=0.001)
        mem._local["old_key"]["timestamp"] = 0  # make it ancient
        await mem.decay()
        assert "old_key" not in mem._local

    def test_stats(self):
        mem = StigmergyMemory(use_chroma=False)
        stats = mem.stats()
        assert "entries" in stats
        assert "has_chroma" in stats


# ── Scaffolder tests ──────────────────────────────────────────────────────────
class TestScaffolder:
    def test_react_scaffold(self, tmp_path):
        s = ProjectScaffolder(str(tmp_path), "my_app", "react")
        files = s.scaffold()
        assert len(files) > 0
        paths = [Path(f) for f in files]
        names = [p.name for p in paths]
        assert "package.json" in names
        assert "vite.config.js" in names

    def test_fullstack_scaffold(self, tmp_path):
        s = ProjectScaffolder(str(tmp_path), "my_app", "fullstack")
        files = s.scaffold()
        names = [Path(f).name for f in files]
        assert "package.json" in names
        assert "main.py" in names

    def test_ml_scaffold(self, tmp_path):
        s = ProjectScaffolder(str(tmp_path), "ml_proj", "ml")
        files = s.scaffold()
        names = [Path(f).name for f in files]
        assert "requirements.txt" in names

    def test_project_name_substitution(self, tmp_path):
        s = ProjectScaffolder(str(tmp_path), "cat_store", "react")
        s.scaffold()
        pkg = Path(s.root_path) / "package.json"
        content = pkg.read_text()
        assert "cat_store" in content


# ── Verifier tests ────────────────────────────────────────────────────────────
class TestVerifier:
    @pytest.mark.asyncio
    async def test_valid_python(self, tmp_path):
        f = tmp_path / "good.py"
        f.write_text("def hello():\n    return 42\n")
        v = Verifier(min_score=0.5)
        result = await v.verify_file(str(f))
        assert result.passed

    @pytest.mark.asyncio
    async def test_invalid_python_syntax(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        v = Verifier(min_score=0.5)
        result = await v.verify_file(str(f))
        assert not result.passed

    @pytest.mark.asyncio
    async def test_missing_file(self, tmp_path):
        v = Verifier()
        result = await v.verify_file(str(tmp_path / "nope.py"))
        assert not result.passed

    @pytest.mark.asyncio
    async def test_markdown_passes(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text("# Hello\nThis is a readme.\n")
        v = Verifier()
        result = await v.verify_file(str(f))
        assert result.passed

    @pytest.mark.asyncio
    async def test_valid_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"name": "test", "version": "1.0"}')
        v = Verifier()
        result = await v.verify_file(str(f))
        assert result.passed

    @pytest.mark.asyncio
    async def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{bad json !!}")
        v = Verifier()
        result = await v.verify_file(str(f))
        assert not result.passed
