"""Central registration of which tools belong to which agent.

Keeping this mapping in one place avoids each agent module re-importing
and re-listing tools ad hoc, and makes it obvious what capability surface
each agent has.
"""
from src.tools.analyst_tools import execute_python_analysis
from src.tools.rag_tools import retrieve_kb_context
from src.tools.sql_tools import run_athena_query

SQL_AGENT_TOOLS = [run_athena_query]
RAG_AGENT_TOOLS = [retrieve_kb_context]
ANALYST_AGENT_TOOLS = [execute_python_analysis]

# Orchestrator holds no tools of its own — it only routes between agents.
ORCHESTRATOR_TOOLS: list = []
