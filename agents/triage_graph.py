from langgraph.graph import StateGraph
from services.symptom_extractor import SymptomExtractor
from services.severity_engine import SeverityEngine
from services.question_generator import generate_followup
from agents.decision_agent import decide_next, doctor_decision
from services.guidance_generator import generate_guidance
from services.doctor_service import DoctorService
from services.confidence_engine import ConfidenceEngine

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------

extractor = SymptomExtractor()
severity_engine = SeverityEngine()
confidence_engine = ConfidenceEngine()
doctor_service = DoctorService()

MAX_FOLLOWUPS = 6

# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------

def opening_node(state):
    print("Agent: What symptom are you currently experiencing?")
    user_input = input("You: ")

    state["conversation_history"] = [user_input]
    state["collected_symptoms"] = extractor.extract(user_input)
    state["asked_questions"] = []

    state["followup_count"] = 0
    state["stop_flag"] = False

    # ✅ Explicit information coverage
    state["info_coverage"] = {
        "duration": False,
        "progression": False,
        "severity": False,
        "red_flags": False
    }

    return state


def followup_node(state):
    state["followup_count"] += 1

    # Safety cap
    if state["followup_count"] >= MAX_FOLLOWUPS:
        state["stop_flag"] = True
        return state

    question = generate_followup(state)

    if question == "STOP":
        state["stop_flag"] = True
        return state

    if question in state["asked_questions"]:
        state["stop_flag"] = True
        return state

    state["asked_questions"].append(question)
    print("Agent:", question)
    user_input = input("You: ")

    state["conversation_history"].append(user_input)

    # Extract symptoms
    new_symptoms = extractor.extract(user_input)
    state["collected_symptoms"].extend(new_symptoms)

    # ------------------------------------------------------------------
    # ✅ Update info coverage (transparent, defensible heuristics)
    # ------------------------------------------------------------------

    text = user_input.lower()

    if any(k in text for k in ["day", "week", "month", "year", "since", "for"]):
        state["info_coverage"]["duration"] = True

    if any(k in text for k in ["worse", "better", "increasing", "decreasing", "same"]):
        state["info_coverage"]["progression"] = True

    if any(k in text for k in ["mild", "moderate", "severe", "pain", "scale"]):
        state["info_coverage"]["severity"] = True

    if any(k in text for k in [
        "chest pain", "faint", "bleeding", "shortness of breath",
        "unconscious", "seizure", "vomiting blood"
    ]):
        state["info_coverage"]["red_flags"] = True

    return state


def should_continue(state):
    # Stop when coverage is complete
    if all(state["info_coverage"].values()):
        return "decide"

    if state.get("stop_flag"):
        return "decide"

    return "followup"


def severity_node(state):
    score, level = severity_engine.calculate(state["collected_symptoms"])
    state["severity_score"] = score
    state["severity_level"] = level

    # Confidence now has real meaning
    state["confidence_score"] = confidence_engine.calculate(state)

    return state


def low_severity_node(state):
    guidance = generate_guidance(state)
    print("\nAgent:", guidance)

    print("\nTriage summary:")
    for k, v in state["info_coverage"].items():
        print(f"- {k}: {'✓' if v else '✗'}")

    if state.get("confidence_score") is not None:
        print(f"\nTriage confidence score: {state['confidence_score']}")
        print("(Reflects information completeness and internal consistency, not a diagnosis.)")

    choice = input(
        "\nAgent: Would you like to see a relevant doctor near you? (yes/no)\nYou: "
    )

    state["want_doctor"] = choice.lower().startswith("y")
    return state


def emergency_node(state):
    print(
        "\nAgent: ⚠️ Your symptoms may indicate a serious condition.\n"
        "This could require immediate medical attention."
    )

    print("\nTriage summary:")
    for k, v in state["info_coverage"].items():
        print(f"- {k}: {'✓' if v else '✗'}")

    if state.get("confidence_score") is not None:
        print(
            f"\nTriage confidence score: {state['confidence_score']}\n"
            "(Reflects consistency and coverage.)"
        )

    choice = input(
        "Agent: Do you want to contact emergency services now? (yes/no)\nYou: "
    )

    if choice.lower().startswith("y"):
        print("\nAgent: Emergency number (Bangladesh): 999")
    else:
        print("\nAgent: Please seek medical care as soon as possible.")

    return state


def ask_location_node(state):
    location = input("\nAgent: Please tell me your location (city/area):\nYou: ")
    state["user_location"] = location
    return state


def doctor_lookup_node(state):
    location = state.get("user_location", "")
    results = doctor_service.find(location, limit=3)

    if results.empty:
        print("\nAgent: No doctors were found for the provided location.")
        return state

    print("\nAgent: Doctors you may consider:\n")

    for _, row in results.iterrows():
        print(f"- Doctor Name: {row['Doctor Name']}")
        print(f"  Speciality: {row['Speciality']}")
        print(f"  Experience: {row['Experience']} years")
        print(f"  Chamber: {row['Chamber']}\n")

    return state


def end_node(state):
    return state

# ------------------------------------------------------------------
# Graph
# ------------------------------------------------------------------

graph = StateGraph(dict)

graph.add_node("opening", opening_node)
graph.add_node("followup", followup_node)
graph.add_node("severity", severity_node)
graph.add_node("low", low_severity_node)
graph.add_node("emergency", emergency_node)
graph.add_node("ask_location", ask_location_node)
graph.add_node("doctor_lookup", doctor_lookup_node)
graph.add_node("end", end_node)

graph.set_entry_point("opening")

graph.add_edge("opening", "followup")

graph.add_conditional_edges(
    "followup",
    should_continue,
    {
        "followup": "followup",
        "decide": "severity"
    }
)

graph.add_conditional_edges(
    "severity",
    decide_next,
    {
        "continue": "followup",
        "low": "low",
        "emergency": "emergency"
    }
)

graph.add_conditional_edges(
    "low",
    doctor_decision,
    {
        "ask_location": "ask_location",
        "end": "end"
    }
)

graph.add_edge("ask_location", "doctor_lookup")
graph.add_edge("doctor_lookup", "end")
graph.add_edge("emergency", "end")

app = graph.compile()
