import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import asyncio

from src.mcp.server import get_portfolio_summary, calculate_org_air_score, get_company_evidence, generate_justification, run_gap_analysis, generate_justification_impl
from src.services.analytics.fund_air import FundAIRCalculator
from src.dashboard.components.evidence_display import (
    render_score_badge,
    render_evidence_cards,
    render_gaps_and_initiatives,
    render_dimension_summary_table,
)

st.set_page_config(page_title="CS5 Portfolio Dashboard", layout="wide")
st.title("CS5 Portfolio Intelligence Dashboard")


def render_portfolio_overview():
    st.header("Portfolio Overview")

    portfolio = get_portfolio_summary("default")
    calc = FundAIRCalculator()
    fund_metrics = calc.calculate(portfolio)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fund-AI-R", fund_metrics["fund_air"])
    c2.metric("Avg Score", fund_metrics["avg_score"])
    c3.metric("% Above Threshold", fund_metrics["pct_above_threshold"])
    c4.metric("Company Count", fund_metrics["count"])

    df = pd.DataFrame(portfolio)
    if not df.empty:
        st.subheader("Portfolio Table")
        st.dataframe(df[["ticker", "name", "sector", "org_air", "vr", "hr", "synergy", "delta", "evidence_count"]], use_container_width=True)

        st.subheader("VR vs HR Scatter")
        fig, ax = plt.subplots()
        ax.scatter(df["vr"], df["hr"])

        for _, row in df.iterrows():
            ax.annotate(row["ticker"], (row["vr"], row["hr"]))

        ax.set_xlabel("VR Score")
        ax.set_ylabel("HR Score")
        ax.set_title("VR vs HR by Company")
        st.pyplot(fig)


def render_company_deep_dive():
    st.header("Company Deep Dive")

    company = st.selectbox("Select Company", ["NVDA", "JPM", "WMT", "GE", "DG"])
    dimension = st.selectbox(
        "Select Dimension",
        [
            "data_infrastructure",
            "ai_governance",
            "technology_stack",
            "talent",
            "leadership",
            "use_case_portfolio",
            "culture",
        ],
    )

    def run_async(coro):
    
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)

    if st.button("Analyze Company"):
        async def run_all():
            scoring = await calculate_org_air_score(company)
            evidence = await get_company_evidence(company)
            justification = await generate_justification_impl(company, dimension)
            gap_analysis =  run_gap_analysis(company, scoring["org_air_score"])
            return scoring, evidence, justification, gap_analysis

        scoring, evidence, justification, gap_analysis = run_async(run_all())

        render_score_badge(scoring["org_air_score"])
        render_dimension_summary_table(scoring.get("dimension_scores", {}))
        render_evidence_cards(evidence)
        render_gaps_and_initiatives(
            gap_analysis.get("gaps", []),
            gap_analysis.get("initiatives", []),
        )

        st.subheader("Justification")
        st.json(justification)


page = st.sidebar.radio(
    "Navigate",
    ["Portfolio Overview", "Company Deep Dive"]
)

if page == "Portfolio Overview":
    render_portfolio_overview()
else:
    render_company_deep_dive()