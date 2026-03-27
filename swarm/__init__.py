"""
SwarmDev — Enterprise Swarm Intelligence Development Framework
1000-agent parallel code generation for any stack.
"""
from .config import SwarmConfig, detect_stack, get_roles_for_stack, AGENT_ROLES
from .executor import SwarmExecutor
from .task_graph import TaskGraph, Task, TaskStatus
from .agents import Agent, AgentPool
from .memory import StigmergyMemory
from .llm_client import LLMClient
from .llm_router import LLMRouter
from .verifier import Verifier
from .scaffolder import ProjectScaffolder

__version__ = "3.0.0"
__all__ = [
    "SwarmConfig", "SwarmExecutor", "TaskGraph", "Task", "TaskStatus",
    "Agent", "AgentPool", "StigmergyMemory", "LLMClient", "LLMRouter",
    "Verifier", "ProjectScaffolder", "detect_stack", "get_roles_for_stack",
    "AGENT_ROLES",
]
