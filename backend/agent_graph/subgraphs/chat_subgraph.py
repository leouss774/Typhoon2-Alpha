"""Sous-graphe : Agent Conversationnel (Agent #3).

Sous-graphe LangGraph indépendant, invoqué à la demande via l'API.
Pioche dans le rapport déjà généré pour répondre aux questions du client.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from backend.agents.conversationnel.agent import repondre_question_client


class ChatState(BaseModel):
    """État du sous-graphe de chat."""

    session_id: str
    question: str = ""
    rapport_contexte: dict = Field(default_factory=dict)
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    reponse: str = ""
    next_node: str = "traiter_question"


def traiter_question_node(state: ChatState) -> dict:
    """Traite la question du client en utilisant le contexte du rapport."""
    reponse = repondre_question_client(
        question=state.question,
        rapport_contexte=state.rapport_contexte,
        historique=state.messages,
    )
    return {
        "reponse": reponse,
        "next_node": "__end__",
    }


def build_chat_subgraph() -> StateGraph:
    """Construit et retourne le sous-graphe de chat."""
    builder = StateGraph(ChatState)

    builder.add_node("traiter_question", traiter_question_node)

    builder.set_entry_point("traiter_question")
    builder.add_conditional_edges(
        "traiter_question",
        lambda s: s.next_node,
        {"__end__": END},
    )

    return builder.compile()
