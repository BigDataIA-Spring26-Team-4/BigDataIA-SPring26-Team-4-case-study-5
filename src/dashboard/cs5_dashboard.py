import json
from typing import Dict, Any

import streamlit as st

from src.agents.graph import DueDiligenceGraphRunner


COMPANIES = ["NVDA", "JPM", "WMT", "GE", "DG"]


def render_metric_cards(scoring: Dict[str, Any]):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Org-AI-R", scoring.get("org_air_score", 0.0))
    col2.metric("VR", scoring.get("vr_score", 0.0))
    col3.metric("HR", scoring.get("hr_score", 0.0))
    col4.metric("Synergy", scoring.get("synergy_score", 0.0))


def render_dimension_scores(dimension_scores: Dict[str, Any]):
    st.subheader("Dimension Scores")

    for dim, details in dimension_scores.items():
        score = details.get("score", 0)
        level = details.get("level", "")
        ci = details.get("confidence_interval", [])
        evidence_count = details.get("evidence_count", 0)

        st.markdown(f"### {dim.replace('_', ' ').title()}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Score", score)
        c2.metric("Level", level)
        c3.metric("Evidence Count", evidence_count)

        if ci and len(ci) == 2:
            st.write(f"Confidence Interval: [{ci[0]}, {ci[1]}]")

        st.progress(min(max(score / 100.0, 0.0), 1.0))
        st.divider()


def render_justifications(justifications: Dict[str, Any]):
    st.subheader("Evidence Justifications")

    for dim, payload in justifications.items():
        with st.expander(dim.replace("_", " ").title(), expanded=False):
            st.write(f"**Score:** {payload.get('score', 'N/A')}")
            st.write(f"**Level:** {payload.get('level_name', 'N/A')}")
            st.write(f"**Evidence Strength:** {payload.get('evidence_strength', 'N/A')}")
            st.write(f"**Rubric Criteria:** {payload.get('rubric_criteria', 'N/A')}")

            rubric_keywords = payload.get("rubric_keywords", [])
            if rubric_keywords:
                st.write("**Rubric Keywords:**")
                st.write(", ".join(rubric_keywords))

            gaps = payload.get("gaps_identified", [])
            if gaps:
                st.write("**Gaps Identified:**")
                for gap in gaps:
                    st.write(f"- {gap}")

            summary = payload.get("generated_summary")
            if summary:
                st.write("**Generated Summary:**")
                st.write(summary)


def render_value_creation(plan: Dict[str, Any]):
    st.subheader("Value Creation Plan")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Gaps")
        gaps = plan.get("gaps", [])
        if gaps:
            for gap in gaps:
                st.write(f"- {gap}")
        else:
            st.write("No major gaps identified.")

    with c2:
        st.markdown("### Initiatives")
        initiatives = plan.get("initiatives", [])
        if initiatives:
            for item in initiatives:
                st.write(f"- {item}")
        else:
            st.write("No initiatives generated.")


def render_message_trace(messages):
    st.subheader("Agent Message Trace")
    for msg in messages:
        st.write(f"**[{msg['agent_name']}]** {msg['content']}")


def render_cs5_dashboard():
    st.title("🤖 CS5 Agentic Due Diligence")
    st.markdown("*LangGraph + MCP + CS1-CS4 Integration*")

    company_id = st.selectbox("Select Company", COMPANIES, key="cs5_company")
    assessment_type = st.selectbox(
        "Assessment Type",
        ["full", "limited", "screening"],
        index=0,
        key="cs5_assessment_type",
    )
    requested_by = st.text_input("Requested By", value="Tapan", key="cs5_requested_by")

    if st.button("Run Agentic Due Diligence", type="primary", key="cs5_run_btn"):
        with st.spinner(f"Running due diligence workflow for {company_id}..."):
            runner = DueDiligenceGraphRunner()
            state = runner.run(
                company_id=company_id,
                assessment_type=assessment_type,
                requested_by=requested_by,
            )

        scoring = state.get("scoring_result", {})
        justifications = state.get("evidence_justifications", {})
        value_plan = state.get("value_creation_plan", {})
        messages = state.get("messages", [])

        st.success(f"Workflow completed for {company_id}")

        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            ["Summary", "Dimensions", "Justifications", "Value Plan", "Trace"]
        )

        with tab1:
            st.subheader("Org-AI-R Summary")
            render_metric_cards(scoring)
            st.json(scoring)

        with tab2:
            render_dimension_scores(scoring.get("dimension_scores", {}))

        with tab3:
            render_justifications(justifications)

        with tab4:
            render_value_creation(value_plan)

        with tab5:
            render_message_trace(messages)

        st.subheader("Full Workflow State")
        st.code(json.dumps(state, indent=2, default=str), language="json")