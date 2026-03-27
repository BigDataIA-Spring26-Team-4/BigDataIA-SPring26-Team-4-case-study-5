"""
Task 9.5: Evidence Display Component (6 pts).

Streamlit component for rendering CS4 justifications with
score badges, evidence cards, gap sections, and confidence indicators.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List

from services.cs4_client import ScoreJustification


# Level → color mapping (L1=red through L5=teal)
LEVEL_COLORS = {
    1: "#ef4444",  # red — Nascent
    2: "#f97316",  # orange — Developing
    3: "#eab308",  # yellow — Adequate
    4: "#22c55e",  # green — Good
    5: "#14b8a6",  # teal — Excellent
}

LEVEL_NAMES = {
    1: "Nascent",
    2: "Developing",
    3: "Adequate",
    4: "Good",
    5: "Excellent",
}

STRENGTH_COLORS = {
    "strong": "#22c55e",
    "moderate": "#eab308",
    "weak": "#ef4444",
    "unknown": "#6b7280",
}


def render_evidence_card(justification: ScoreJustification) -> None:
    """
    Render a single dimension's evidence card.

    Shows:
      - Score badge with color coding (L1-L5)
      - Evidence list with source citations
      - Gaps identified section
      - Confidence indicator
    """
    color = LEVEL_COLORS.get(justification.level, "#6b7280")
    level_name = LEVEL_NAMES.get(justification.level, "Unknown")

    with st.container():
        # ── Header row: dimension name + score badge + score value ──
        col1, col2, col3 = st.columns([4, 1, 1])

        with col1:
            dim_title = justification.dimension.replace("_", " ").title()
            st.markdown(f"### {dim_title}")

        with col2:
            st.markdown(
                f'<span style="background-color:{color};color:white;'
                f'padding:4px 12px;border-radius:12px;font-weight:bold;">'
                f'L{justification.level}</span>',
                unsafe_allow_html=True,
            )

        with col3:
            st.markdown(f"**{justification.score:.1f}**")

        # ── Evidence strength indicator ──
        strength = justification.evidence_strength
        str_color = STRENGTH_COLORS.get(strength, "#6b7280")
        st.markdown(
            f"Evidence: <span style='color:{str_color}'>"
            f"**{strength.title()}**</span>",
            unsafe_allow_html=True,
        )

        # ── Rubric criteria ──
        if justification.rubric_criteria:
            st.info(f"**Rubric Match:** {justification.rubric_criteria}")

        # ── Supporting evidence (from CS4 RAG) ──
        if justification.supporting_evidence:
            st.markdown("**Supporting Evidence:**")
            for i, evidence in enumerate(justification.supporting_evidence[:5], 1):
                label = f"[{evidence.source_type}] {evidence.content[:60]}..."
                with st.expander(label, expanded=False):
                    st.write(evidence.content)
                    st.caption(f"Confidence: {evidence.confidence:.0%}")
                    if evidence.source_url:
                        st.markdown(f"[Source]({evidence.source_url})")

        # ── Gaps identified ──
        if justification.gaps_identified:
            st.warning("**Gaps Identified:**")
            for gap in justification.gaps_identified:
                st.markdown(f"- {gap}")

        st.divider()


def render_company_evidence_panel(
    company_id: str,
    justifications: Dict[str, ScoreJustification],
) -> None:
    """
    Render full evidence panel for a company.

    Shows summary metrics and all 7 dimensions with tabbed navigation.
    """
    st.header(f"Evidence Analysis: {company_id}")

    # ── Summary metrics row ──
    total_evidence = sum(
        len(j.supporting_evidence) for j in justifications.values()
    )
    avg_level = sum(j.level for j in justifications.values()) / max(
        len(justifications), 1
    )
    strong_count = sum(
        1 for j in justifications.values() if j.evidence_strength == "strong"
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Evidence", total_evidence)
    col2.metric("Avg Level", f"L{avg_level:.1f}")
    col3.metric("Strong Evidence", f"{strong_count}/{len(justifications)}")
    col4.metric("Dimensions", len(justifications))

    # ── Dimension tabs ──
    if justifications:
        dim_names = [d.replace("_", " ").title() for d in justifications.keys()]
        tabs = st.tabs(dim_names)

        for tab, (dim, just) in zip(tabs, justifications.items()):
            with tab:
                render_evidence_card(just)


def render_evidence_summary_table(
    justifications: Dict[str, ScoreJustification],
) -> None:
    """Render compact summary table of all dimensions with color coding."""
    data = []
    for dim, just in justifications.items():
        data.append({
            "Dimension": dim.replace("_", " ").title(),
            "Score": just.score,
            "Level": f"L{just.level}",
            "Evidence": just.evidence_strength.title(),
            "Items": len(just.supporting_evidence),
            "Gaps": len(just.gaps_identified),
        })

    df = pd.DataFrame(data)

    # Color-code the Level column
    def color_level(val):
        try:
            level = int(val[1])
            return f"background-color: {LEVEL_COLORS.get(level, '#ffffff')}; color: white;"
        except (ValueError, IndexError):
            return ""

    styled = df.style.applymap(color_level, subset=["Level"])
    st.dataframe(styled, use_container_width=True, hide_index=True)
