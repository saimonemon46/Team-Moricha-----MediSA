# ============================================================
# MediAI — LangGraph Workflow
# Orchestrates the multi-step AI triage pipeline
# ============================================================

import uuid
import json
from datetime import datetime
from typing import TypedDict, List, Annotated, Optional
import operator

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_pipeline.rag_engine import retrieve, format_context
from fastapi_ai.models.llm_client import chat_json, chat
from fastapi_ai.prompts.templates import (
    FOLLOWUP_QUESTIONS_SYSTEM, FOLLOWUP_QUESTIONS_USER,
    TRIAGE_ANALYSIS_SYSTEM, TRIAGE_ANALYSIS_USER,
    EXPLANATION_SYSTEM, EXPLANATION_USER,
)


# ---- State schema ----

class TriageState(TypedDict):
    session_id: str
    user_id: int
    primary_symptom: str
    followup_questions: List[str]
    user_answers: List[str]
    retrieved_context: str
    triage_result: dict
    explanation: str
    report: dict
    error: Optional[str]


# ---- Node functions ----

def node_rag_retrieval(state: TriageState) -> TriageState:
    """Retrieve relevant medical knowledge from vector store."""
    query = state["primary_symptom"]
    if state.get("user_answers"):
        query += " " + " ".join(state["user_answers"])
    docs = retrieve(query, top_k=6)
    state["retrieved_context"] = format_context(docs)
    return state


def node_generate_questions(state: TriageState) -> TriageState:
    """Generate follow-up questions using LLM + RAG context."""
    prompt_user = FOLLOWUP_QUESTIONS_USER.format(
        symptom=state["primary_symptom"],
        context=state["retrieved_context"]
    )
    try:
        result = chat_json(FOLLOWUP_QUESTIONS_SYSTEM, prompt_user)
        questions = result.get("questions", [])
        if not questions:
            questions = [
                f"How long have you been experiencing {state['primary_symptom']}?",
                "On a scale of 1 to 10, how severe is the discomfort?",
                "Do you have any other symptoms such as fever, nausea, or fatigue?"
            ]
    except Exception as e:
        questions = [
            f"How long have you been experiencing {state['primary_symptom']}?",
            "On a scale of 1 to 10, how severe is the discomfort?",
            "Do you have any other symptoms such as fever, nausea, or fatigue?"
        ]
    state["followup_questions"] = questions
    return state


def node_process_answers(state: TriageState) -> TriageState:
    """Re-retrieve context enriched by user answers."""
    enriched_query = state["primary_symptom"] + " " + " ".join(state.get("user_answers", []))
    docs = retrieve(enriched_query, top_k=8)
    state["retrieved_context"] = format_context(docs)
    return state


def node_triage_engine(state: TriageState) -> TriageState:
    """Run triage analysis using LLM + enriched RAG context."""
    answers_text = "\n".join(
        f"Q{i+1}: {q}\nA: {a}"
        for i, (q, a) in enumerate(zip(
            state.get("followup_questions", []),
            state.get("user_answers", [])
        ))
    ) or "No follow-up answers provided."

    prompt_user = TRIAGE_ANALYSIS_USER.format(
        symptom=state["primary_symptom"],
        answers=answers_text,
        context=state["retrieved_context"]
    )

    try:
        result = chat_json(TRIAGE_ANALYSIS_SYSTEM, prompt_user, max_tokens=1024)
        if not result.get("possible_condition"):
            raise ValueError("Empty triage result")
    except Exception:
        result = {
            "possible_condition": "Undetermined — insufficient information",
            "urgency": "medium",
            "recommended_specialist": "General Physician",
            "reasoning": "Based on the symptoms described and retrieved medical knowledge, a definitive assessment could not be determined. Professional evaluation is recommended.",
            "guidance": "Please consult a General Physician for a thorough in-person examination.",
            "symptoms_listed": [state["primary_symptom"]]
        }

    state["triage_result"] = result
    return state


def node_generate_explanation(state: TriageState) -> TriageState:
    """Generate a patient-friendly explanation."""
    try:
        explanation = chat(
            EXPLANATION_SYSTEM,
            EXPLANATION_USER.format(
                triage_result=json.dumps(state["triage_result"]),
                context=state["retrieved_context"][:800]
            ),
            max_tokens=300
        )
    except Exception:
        r = state["triage_result"]
        explanation = (
            f"Based on your symptoms, the assessment suggests {r.get('possible_condition', 'an unspecified condition')}. "
            f"The urgency level is {r.get('urgency', 'medium')}. "
            f"It is recommended you consult a {r.get('recommended_specialist', 'General Physician')}."
        )
    state["explanation"] = explanation
    return state


def node_generate_report(state: TriageState) -> TriageState:
    """Compile the final structured report."""
    r = state["triage_result"]
    state["report"] = {
        "session_id":            state["session_id"],
        "user_id":               state["user_id"],
        "possible_condition":    r.get("possible_condition", "Unknown"),
        "urgency":               r.get("urgency", "medium"),
        "recommended_specialist":r.get("recommended_specialist", "General Physician"),
        "reasoning":             r.get("reasoning", ""),
        "guidance":              r.get("guidance", ""),
        "symptoms_listed":       r.get("symptoms_listed", [state["primary_symptom"]]),
        "explanation":           state.get("explanation", ""),
        "generated_at":          datetime.utcnow().isoformat() + "Z",
    }
    return state


# ---- Graph construction ----

def build_graph():
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(TriageState)

    graph.add_node("rag_retrieval",         node_rag_retrieval)
    graph.add_node("generate_questions",    node_generate_questions)
    graph.add_node("process_answers",       node_process_answers)
    graph.add_node("triage_engine",         node_triage_engine)
    graph.add_node("generate_explanation",  node_generate_explanation)
    graph.add_node("generate_report",       node_generate_report)

    graph.set_entry_point("rag_retrieval")
    graph.add_edge("rag_retrieval",        "generate_questions")
    graph.add_edge("generate_questions",   END)          # pause — wait for user answers

    return graph.compile()


def build_report_graph():
    """Separate graph for the report generation phase (after answers collected)."""
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(TriageState)

    graph.add_node("process_answers",       node_process_answers)
    graph.add_node("triage_engine",         node_triage_engine)
    graph.add_node("generate_explanation",  node_generate_explanation)
    graph.add_node("generate_report",       node_generate_report)

    graph.set_entry_point("process_answers")
    graph.add_edge("process_answers",      "triage_engine")
    graph.add_edge("triage_engine",        "generate_explanation")
    graph.add_edge("generate_explanation", "generate_report")
    graph.add_edge("generate_report",      END)

    return graph.compile()


# ---- High-level API functions ----

def run_question_generation(symptom: str, user_id: int, session_id: str = None) -> dict:
    """Run the question generation phase of the pipeline."""
    if session_id is None:
        session_id = str(uuid.uuid4())[:8].upper()

    state: TriageState = {
        "session_id":          session_id,
        "user_id":             user_id,
        "primary_symptom":     symptom,
        "followup_questions":  [],
        "user_answers":        [],
        "retrieved_context":   "",
        "triage_result":       {},
        "explanation":         "",
        "report":              {},
        "error":               None,
    }

    graph = build_graph()
    if graph:
        final_state = graph.invoke(state)
    else:
        # Manual execution when LangGraph not available
        state = node_rag_retrieval(state)
        state = node_generate_questions(state)
        final_state = state

    return {
        "session_id": final_state["session_id"],
        "questions":  final_state["followup_questions"],
    }


def run_report_generation(session_id: str, symptom: str, answers: list, user_id: int) -> dict:
    """Run the full triage analysis and report generation phase."""
    state: TriageState = {
        "session_id":          session_id,
        "user_id":             user_id,
        "primary_symptom":     symptom,
        "followup_questions":  [],
        "user_answers":        answers,
        "retrieved_context":   "",
        "triage_result":       {},
        "explanation":         "",
        "report":              {},
        "error":               None,
    }

    graph = build_report_graph()
    if graph:
        final_state = graph.invoke(state)
    else:
        state = node_process_answers(state)
        state = node_triage_engine(state)
        state = node_generate_explanation(state)
        state = node_generate_report(state)
        final_state = state

    return {"report": final_state["report"]}
