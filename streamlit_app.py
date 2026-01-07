import streamlit as st
from agents.triage_graph import app as triage_app

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="AI Medical Triage",
    page_icon="🩺",
    layout="centered"
)

st.title("🩺 AI Medical Triage Assistant")
st.caption("General guidance only. Not a medical diagnosis.")

# -----------------------------
# Initialize session state
# -----------------------------
if "state" not in st.session_state:
    st.session_state.state = {
        "conversation_history": [],
        "collected_symptoms": [],
        "asked_questions": [],
        "followup_count": 0,
        "stop_flag": False,
        "severity_score": None,
        "severity_level": None,
        "confidence_score": None,
        "want_doctor": False,
        "user_location": None
    }

if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------
# Display conversation
# -----------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------------
# User input
# -----------------------------
user_input = st.chat_input("Describe your symptom or answer the question above")

if user_input:
    # Show user message
    st.session_state.messages.append({
        "role": "user",
        "content": user_input
    })

    # Update state for graph
    st.session_state.state["conversation_history"].append(user_input)

    # Run LangGraph step
    updated_state = triage_app.invoke(st.session_state.state)

    st.session_state.state = updated_state

    # Detect what the agent just did
    last_agent_output = None

    if "agent_message" in updated_state:
        last_agent_output = updated_state["agent_message"]

    # Fallback: use guidance or prompts
    if updated_state.get("severity_level") and updated_state.get("stop_flag"):
        if updated_state["severity_level"] == "high":
            last_agent_output = (
                "⚠️ This may be a medical emergency.\n\n"
                "If you are experiencing severe or rapidly worsening symptoms, "
                "please consider contacting emergency services immediately."
            )
        else:
            last_agent_output = updated_state.get(
                "guidance_text",
                "Here is some general guidance based on what you shared."
            )

            if updated_state.get("confidence_score") is not None:
                last_agent_output += (
                    f"\n\n**Triage confidence:** {updated_state['confidence_score']}"
                )

    if last_agent_output:
        st.session_state.messages.append({
            "role": "assistant",
            "content": last_agent_output
        })

    st.rerun()
