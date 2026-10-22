"""LangGraph graph tanımı: router → (retrieve → qa | summarize | extract_actions | compare)."""

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    compare_node,
    extract_actions_node,
    qa_node,
    retrieve_node,
    route_after_router,
    router_node,
    summarize_node,
)
from app.agent.state import AgentState


def build_agent_graph():
    """Agent graph'ını kurar ve compile eder."""
    g = StateGraph(AgentState)
    g.add_node("router", router_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("qa", qa_node)
    g.add_node("summarize", summarize_node)
    g.add_node("extract_actions", extract_actions_node)
    g.add_node("compare", compare_node)

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "qa": "retrieve",
            "summarize": "retrieve",
            "extract_actions": "retrieve",
            "compare": "retrieve",
        },
    )
    # retrieve sonrası intent'e göre uzman node'a dallan
    g.add_conditional_edges(
        "retrieve",
        route_after_router,
        {
            "qa": "qa",
            "summarize": "summarize",
            "extract_actions": "extract_actions",
            "compare": "compare",
        },
    )
    g.add_edge("qa", END)
    g.add_edge("summarize", END)
    g.add_edge("extract_actions", END)
    g.add_edge("compare", END)

    return g.compile()


AGENT_GRAPH = build_agent_graph()  # modül seviyesinde compile et
