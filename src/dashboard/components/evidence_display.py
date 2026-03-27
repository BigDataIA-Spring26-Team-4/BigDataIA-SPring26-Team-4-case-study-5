import streamlit as st


def render_score_badge(score: float, label: str = "Org-AI-R"):
    if score >= 75:
        color = "🟢"
    elif score >= 60:
        color = "🟡"
    else:
        color = "🔴"

    st.markdown(f"### {color} {label}: {score:.2f}")


def render_evidence_cards(evidence: list):
    st.subheader("Evidence")
    if not evidence:
        st.info("No evidence available.")
        return

    for idx, item in enumerate(evidence[:10], start=1):
        with st.container():
            st.markdown(f"**Evidence #{idx}**")
            st.write(f"**Source Type:** {item.get('source_type', 'N/A')}")
            st.write(f"**Signal Category:** {item.get('signal_category', 'N/A')}")
            st.write(f"**Confidence:** {item.get('confidence', 0.0)}")
            st.write(item.get("content", ""))
            st.divider()


def render_gaps_and_initiatives(gaps: list, initiatives: list):
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Gaps")
        if gaps:
            for gap in gaps:
                st.write(f"- {gap}")
        else:
            st.write("No major gaps identified.")

    with c2:
        st.subheader("Initiatives")
        if initiatives:
            for item in initiatives:
                st.write(f"- {item}")
        else:
            st.write("No initiatives available.")


def render_dimension_summary_table(dimension_scores: dict):
    st.subheader("Dimension Summary")

    if not dimension_scores:
        st.info("No dimension scores available.")
        return

    rows = []
    for dim, payload in dimension_scores.items():
        if isinstance(payload, dict):
            score = payload.get("score", 0)
            level = payload.get("level", "")
            evidence_count = payload.get("evidence_count", 0)
            confidence_interval = payload.get("confidence_interval", [])
        else:
            score = getattr(payload, "score", 0)
            level_obj = getattr(payload, "level", "")
            level = getattr(level_obj, "value", level_obj)
            evidence_count = getattr(payload, "evidence_count", 0)
            confidence_interval = getattr(payload, "confidence_interval", [])

        rows.append(
            {
                "Dimension": getattr(dim, "value", str(dim)),
                "Score": score,
                "Level": level,
                "Evidence Count": evidence_count,
                "Confidence Interval": confidence_interval,
            }
        )

    st.dataframe(rows, width="stretch")