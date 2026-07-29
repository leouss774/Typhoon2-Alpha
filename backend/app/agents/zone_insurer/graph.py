"""
StateGraph LangGraph pour le zone-insurer :
zone_resolver -> collector_fanout -> aggregator -> report
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.zone_insurer import (
    aggregator_agent,
    collector_fanout_agent,
    report_agent,
    zone_resolver_agent,
)
from app.agents.zone_insurer.state import ZoneState


def build_graph():
    graph = StateGraph(ZoneState)

    graph.add_node("zone_resolver", zone_resolver_agent.run)
    graph.add_node("collector_fanout", collector_fanout_agent.run)
    graph.add_node("aggregator", aggregator_agent.run)
    graph.add_node("report", report_agent.run)

    graph.set_entry_point("zone_resolver")
    graph.add_edge("zone_resolver", "collector_fanout")
    graph.add_edge("collector_fanout", "aggregator")
    graph.add_edge("aggregator", "report")
    graph.add_edge("report", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
