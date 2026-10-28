import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st

from config.settings import settings

API_BASE = settings.BACKEND_BASE_URL

st.set_page_config(page_title="Personalized Study Guide Generator", layout="wide")
st.title("📚 Personalized Study Guide Generator")

if "user_id" not in st.session_state:
    st.session_state.user_id = "demo_user"

tab_generate, tab_progress = st.tabs(["Generate", "My Progress"])

# ----------------------------------------------------------------- Generate
with tab_generate:
    st.session_state.user_id = st.text_input("User ID", value=st.session_state.user_id)

    topic = st.text_input("Topic", placeholder="e.g. Convolutional Neural Networks")

    st.markdown("**Learning Goal**")
    goal_labels = {
        "understand_concepts": "Understand concepts",
        "prepare_interview": "Prepare for interview",
        "prepare_exam": "Prepare for exam",
        "learn_implementation": "Learn for implementation",
    }
    selected_goals = [
        key for key, label in goal_labels.items() if st.checkbox(label, key=f"goal_{key}")
    ]

    col1, col2 = st.columns(2)
    with col1:
        current_knowledge = st.selectbox("Current Knowledge", ["beginner", "intermediate", "advanced"])
        learning_style = st.selectbox("Preferred Learning Style", ["conceptual", "examples", "code_heavy", "mixed"])
    with col2:
        available_time = st.selectbox("Available Time", ["30_min", "1_hour", "3_hours", "1_week"])
        difficulty = st.selectbox("Difficulty", ["beginner", "intermediate", "advanced"])

    st.markdown("**Generate**")
    output_labels = {
        "study_guide": "Study Guide",
        "flashcards": "Flashcards",
        "quiz": "Quiz",
        "interview_questions": "Interview Questions",
        "revision_notes": "Revision Notes",
        "practical_exercises": "Practical Exercises",
        "cheat_sheet": "Cheat Sheet",
    }
    selected_outputs = [
        key for key, label in output_labels.items() if st.checkbox(label, key=f"out_{key}", value=(key == "study_guide"))
    ]

    if st.button("Generate Study Materials", type="primary"):
        if not topic or not selected_goals or not selected_outputs:
            st.warning("Please provide a topic, at least one goal, and at least one output type.")
        else:
            payload = {
                "user_id": st.session_state.user_id,
                "topic": topic,
                "learning_goals": selected_goals,
                "current_knowledge": current_knowledge,
                "available_time": available_time,
                "learning_style": learning_style,
                "difficulty": difficulty,
                "outputs_requested": selected_outputs,
            }
            with st.spinner("Planning, retrieving, and generating your study materials..."):
                try:
                    resp = requests.post(f"{API_BASE}/generate-guide", json=payload, timeout=300)
                    resp.raise_for_status()
                    result = resp.json()
                    st.session_state.last_result = result
                except requests.RequestException as e:
                    st.error(f"Request failed: {e}")

    if "last_result" in st.session_state:
        result = st.session_state.last_result
        st.success(f"Generated (guide_id: {result['guide_id']})")
        out_tabs = st.tabs(list(result["outputs"].keys()))
        for tab, (output_type, content) in zip(out_tabs, result["outputs"].items()):
            with tab:
                if isinstance(content, str):
                    st.markdown(content)
                else:
                    st.json(content)
                qr = result["quality_results"].get(output_type)
                if qr and not qr.get("passed", True):
                    st.warning(f"Quality check flagged issues: {qr.get('issues')}")

# ------------------------------------------------------------------ Progress
with tab_progress:
    st.subheader("My Progress")
    if st.button("Refresh Progress"):
        try:
            resp = requests.get(f"{API_BASE}/progress/{st.session_state.user_id}", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            col_weak, col_strong = st.columns(2)
            with col_weak:
                st.markdown("### 🔴 Weak Topics")
                for t in data.get("weak_topics", []):
                    st.write(f"- {t}")
            with col_strong:
                st.markdown("### 🟢 Strong Topics")
                for t in data.get("strong_topics", []):
                    st.write(f"- {t}")
        except requests.RequestException as e:
            st.error(f"Request failed: {e}")
