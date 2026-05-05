"""MCB Tutor agent — route -> retrieve -> rerank -> generate pipeline."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from apps.api.agent.nodes.generate import generate_node
from apps.api.agent.nodes.rerank import rerank_node
from apps.api.agent.nodes.retrieve import retrieve_node
from apps.api.agent.nodes.route import route_node
from apps.api.agent.state import AgentState


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("route", route_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("rerank", rerank_node)
    g.add_node("generate", generate_node)
    g.add_edge(START, "route")
    g.add_edge("route", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", END)
    return g.compile()


tutor_graph = build_graph()


def run_agent(
    *,
    messages: list[dict],
    course: str,
    user_id: str,
    user_doc_texts: list[str] | None = None,
) -> dict:
    """Run the pipeline synchronously.

    messages: [{"role": "user"|"assistant", "content": str}, ...]
    Returns:  {"draft", "citations", "attachments", "intent"}
    """
    lc_messages = [
        HumanMessage(content=m["content"]) if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in messages
    ]
    result = tutor_graph.invoke({
        "messages": lc_messages,
        "course": course,
        "user_id": user_id,
        "user_doc_texts": user_doc_texts or [],
    })
    return {
        "draft":       result.get("draft", ""),
        "citations":   result.get("citations", []),
        "attachments": result.get("attachments", []),
        "intent":      result.get("intent", "unknown"),
    }
