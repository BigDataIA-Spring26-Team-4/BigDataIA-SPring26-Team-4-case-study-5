"""
Task 9.6: Portfolio Intelligence Dashboard (10 pts).

Streamlit dashboard showing portfolio overview with data from CS1-CS4.
ALL DATA comes from PortfolioDataService (no mock data).

Run: streamlit run cs5/src/dashboard/app.py

v4 FIX: Uses nest_asyncio for Streamlit async compatibility.
"""

import sys
from pathlib import Path

# Ensure cs5/src is importable
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st
import plotly.express as px
import pandas as pd
import asyncio

# v4 FIX: Required for Streamlit + async compatibility
import nest_asyncio
nest_asyncio.apply()

from services.integration.portfolio_data_service import portfolio_data_service
from services.tracking.assessment_history import create_history_service
from services.cs3_client import CS3Client
from config import settings

# ── Page config ─────────────────────────────────────────────────

st.set_page_config(
    page_title="PE Org-AI-R Dashboard",
    page_icon="\U0001F4C8",  # chart_with_upwards_trend
    layout="wide",
)

# ── Sidebar ─────────────────────────────────────────────────────

st.sidebar.title("PE Org-AI-R")
st.sidebar.markdown("**Portfolio Intelligence Dashboard**")
fund_id = st.sidebar.text_input("Fund ID", value="growth_fund_v")


# ── Async data loading ──────────────────────────────────────────

@st.cache_data(ttl=300)
def load_portfolio(_fund_id: str) -> pd.DataFrame:
    """Load portfolio data synchronously for Streamlit.

    v4 FIX: Uses nest_asyncio + new event loop pattern
    to bridge Streamlit's sync world with our async clients.
    """
    async def _load():
        return await portfolio_data_service.get_portfolio_view(_fund_id)

    loop = asyncio.get_event_loop()
    portfolio = loop.run_until_complete(_load())
    return pd.DataFrame([
        {
            "ticker": c.ticker,
            "name": c.name,
            "sector": c.sector,
            "org_air": c.org_air,
            "vr_score": c.vr_score,
            "hr_score": c.hr_score,
            "synergy": c.synergy_score,
            "delta": c.delta_since_entry,
            "evidence_count": c.evidence_count,
        }
        for c in portfolio
    ])


# ── Load data ───────────────────────────────────────────────────

try:
    portfolio_df = load_portfolio(fund_id)
    st.sidebar.success(f"Loaded {len(portfolio_df)} companies from CS1-CS4")
except Exception as e:
    st.error(f"Failed to connect to CS1-CS4: {e}")
    st.info("Ensure CS1, CS2, CS3 services are running (Docker: `docker compose up`).")
    st.stop()

if portfolio_df.empty:
    st.warning("No portfolio data returned. Check that companies are loaded in Snowflake.")
    st.stop()


# ── Main content ────────────────────────────────────────────────

st.title("Portfolio Overview")

# ── Metrics row ─────────────────────────────────────────────────

fund_air = portfolio_df["org_air"].mean()
avg_vr = portfolio_df["vr_score"].mean()
avg_delta = portfolio_df["delta"].mean()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Fund-AI-R", f"{fund_air:.1f}")
with col2:
    st.metric("Companies", len(portfolio_df))
with col3:
    st.metric("Avg V\u1D3F", f"{avg_vr:.1f}")
with col4:
    st.metric("Avg Delta", f"{avg_delta:+.1f}")

st.divider()

# ── V^R vs H^R Scatter Plot ────────────────────────────────────

st.subheader("AI-Readiness Map (V\u1D3F vs H\u1D3F)")

fig = px.scatter(
    portfolio_df,
    x="vr_score",
    y="hr_score",
    size="org_air",
    color="sector",
    hover_name="name",
    hover_data={"org_air": ":.1f", "delta": ":+.1f", "evidence_count": True},
    title="Portfolio AI-Readiness Map (from CS3)",
    labels={
        "vr_score": "V\u1D3F (Idiosyncratic)",
        "hr_score": "H\u1D3F (Systematic)",
    },
)

# Threshold lines at 60
fig.add_hline(
    y=60, line_dash="dash", line_color="gray",
    annotation_text="H\u1D3F Threshold",
)
fig.add_vline(
    x=60, line_dash="dash", line_color="gray",
    annotation_text="V\u1D3F Threshold",
)

fig.update_layout(height=500)
st.plotly_chart(fig, use_container_width=True)

# ── Company table with conditional formatting ───────────────────

st.subheader("Portfolio Companies")

# Format for display
display_df = portfolio_df.copy()
display_df = display_df.rename(columns={
    "ticker": "Ticker",
    "name": "Company",
    "sector": "Sector",
    "org_air": "Org-AI-R",
    "vr_score": "V\u1D3F",
    "hr_score": "H\u1D3F",
    "synergy": "Synergy",
    "delta": "\u0394 Entry",
    "evidence_count": "Evidence",
})

st.dataframe(
    display_df.style.background_gradient(
        subset=["Org-AI-R"], cmap="RdYlGn"
    ),
    use_container_width=True,
    hide_index=True,
)

# ── Sector distribution ────────────────────────────────────────

st.subheader("Sector Distribution")

col_left, col_right = st.columns(2)

with col_left:
    sector_counts = portfolio_df["sector"].value_counts()
    fig_pie = px.pie(
        values=sector_counts.values,
        names=sector_counts.index,
        title="Companies by Sector",
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    fig_bar = px.bar(
        portfolio_df.sort_values("org_air", ascending=True),
        x="org_air",
        y="ticker",
        orientation="h",
        color="org_air",
        color_continuous_scale="RdYlGn",
        title="Org-AI-R by Company",
        labels={"org_air": "Org-AI-R", "ticker": ""},
    )
    fig_bar.update_layout(showlegend=False)
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Footer ──────────────────────────────────────────────────────

st.divider()
st.caption("All data from CS1-CS4 via PortfolioDataService. No mock data.")
