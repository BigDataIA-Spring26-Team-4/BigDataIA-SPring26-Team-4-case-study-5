"""
Bonus Extension: LP Letter Generator (+5 pts).

Generates a Limited Partner investor letter from portfolio data.
Summarizes fund-level AI-readiness metrics, company highlights,
and value creation progress.

Uses CS1-CS4 data via PortfolioDataService + Fund-AI-R Calculator.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from typing import Optional
import structlog

from services.integration.portfolio_data_service import (
    portfolio_data_service,
    PortfolioCompanyView,
)
from services.analytics.fund_air import fund_air_calculator

logger = structlog.get_logger()


class LPLetterGenerator:
    """
    Generates quarterly LP letters from portfolio data.

    The letter includes:
      - Fund overview with Fund-AI-R
      - Portfolio company summary table
      - AI leaders and laggards highlights
      - Sector distribution and concentration
      - Value creation progress
      - Outlook
    """

    async def generate(
        self,
        fund_id: str = "growth_fund_v",
        quarter: str = "Q1 2026",
        gp_name: str = "PE Org-AI-R Fund V",
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate a complete LP letter.

        All data comes from CS1-CS4 via PortfolioDataService.

        Args:
            fund_id: Fund identifier
            quarter: Reporting quarter label
            gp_name: General Partner / fund name
            output_path: Optional file path to save

        Returns:
            Formatted markdown string
        """
        logger.info("lp_letter_start", fund_id=fund_id, quarter=quarter)

        # Fetch portfolio data from CS1-CS4
        portfolio = await portfolio_data_service.get_portfolio_view(fund_id)

        # Calculate Fund-AI-R metrics
        # Default EVs for our 5 companies (in $MM)
        default_evs = {
            "NVDA": 2800000.0, "JPM": 650000.0, "WMT": 450000.0,
            "GE": 180000.0, "DG": 30000.0,
        }
        ev_map = {c.company_id: default_evs.get(c.ticker, 100.0) for c in portfolio}

        fund_metrics = fund_air_calculator.calculate_fund_metrics(
            fund_id=fund_id,
            companies=portfolio,
            enterprise_values=ev_map,
        )

        # Build the letter
        letter = self._format_letter(
            portfolio=portfolio,
            metrics=fund_metrics,
            quarter=quarter,
            gp_name=gp_name,
        )

        if output_path:
            Path(output_path).write_text(letter, encoding="utf-8")
            logger.info("lp_letter_saved", path=output_path)

        logger.info("lp_letter_complete", fund_id=fund_id)
        return letter

    def _format_letter(self, portfolio, metrics, quarter, gp_name) -> str:
        """Format the LP letter as markdown."""
        now = datetime.utcnow().strftime("%B %d, %Y")

        # Sort companies by Org-AI-R for highlights
        sorted_cos = sorted(portfolio, key=lambda c: c.org_air, reverse=True)
        leaders = [c for c in sorted_cos if c.org_air >= 70]
        laggards = [c for c in sorted_cos if c.org_air < 50]

        # Sector breakdown
        sectors = {}
        for c in portfolio:
            sectors[c.sector] = sectors.get(c.sector, 0) + 1

        letter = f"""# {gp_name}
## Quarterly LP Letter — {quarter}

**Date:** {now}
**Fund-AI-R:** {metrics.fund_air:.1f}
**Portfolio Companies:** {metrics.company_count}

---

Dear Limited Partners,

We are pleased to provide this quarterly update on the AI-readiness of our portfolio companies as measured by the Org-AI-R framework.

## Fund Overview

The fund's aggregate AI-readiness score (**Fund-AI-R**) stands at **{metrics.fund_air:.1f}** as of this reporting period, based on enterprise-value-weighted averaging across {metrics.company_count} portfolio companies.

| Metric | Value |
|--------|-------|
| Fund-AI-R (EV-Weighted) | **{metrics.fund_air:.1f}** |
| Portfolio Companies | {metrics.company_count} |
| AI Leaders (≥70) | {metrics.ai_leaders_count} |
| AI Laggards (<50) | {metrics.ai_laggards_count} |
| Avg Δ Since Entry | {metrics.avg_delta_since_entry:+.1f} |
| Sector HHI | {metrics.sector_hhi:.4f} |

### Quartile Distribution

| Quartile | Count | Description |
|----------|-------|-------------|
| Q1 (Top) | {metrics.quartile_distribution.get(1, 0)} | Above sector benchmark |
| Q2 | {metrics.quartile_distribution.get(2, 0)} | On track |
| Q3 | {metrics.quartile_distribution.get(3, 0)} | Below benchmark |
| Q4 (Bottom) | {metrics.quartile_distribution.get(4, 0)} | Requires intervention |

---

## Portfolio Summary

| Company | Sector | Org-AI-R | V^R | H^R | Δ Entry | Evidence |
|---------|--------|----------|-----|-----|---------|----------|
"""
        for c in sorted_cos:
            sector_label = c.sector.replace("_", " ").title()
            letter += (
                f"| {c.name} ({c.ticker}) | {sector_label} "
                f"| {c.org_air:.1f} | {c.vr_score:.1f} | {c.hr_score:.1f} "
                f"| {c.delta_since_entry:+.1f} | {c.evidence_count} |\n"
            )

        # Leaders section
        if leaders:
            letter += "\n---\n\n## AI Leaders\n\n"
            letter += "Companies scoring ≥70 on Org-AI-R demonstrate strong AI-readiness foundations:\n\n"
            for c in leaders:
                letter += (
                    f"- **{c.name} ({c.ticker})**: Org-AI-R {c.org_air:.1f} "
                    f"(V^R: {c.vr_score:.1f}, H^R: {c.hr_score:.1f}). "
                    f"Improved {c.delta_since_entry:+.1f} points since entry.\n"
                )

        # Laggards section
        if laggards:
            letter += "\n## Companies Requiring Attention\n\n"
            letter += "Companies scoring <50 require focused AI-readiness investment:\n\n"
            for c in laggards:
                letter += (
                    f"- **{c.name} ({c.ticker})**: Org-AI-R {c.org_air:.1f}. "
                    f"Active improvement initiatives underway with focus on "
                    f"closing the {75 - c.org_air:.0f}-point gap to target.\n"
                )

        letter += f"""
---

## Sector Distribution

"""
        for sector, count in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
            sector_label = sector.replace("_", " ").title()
            letter += f"- **{sector_label}**: {count} companies\n"

        letter += f"""
Sector concentration (HHI) of {metrics.sector_hhi:.4f} indicates {"concentrated" if metrics.sector_hhi > 0.25 else "diversified"} exposure.

---

## Outlook

Our AI-readiness improvement programs continue across the portfolio. Key focus areas for the coming quarter include:

1. **Accelerating laggards**: Implementing 100-day improvement plans for companies below the 50-point threshold
2. **Sustaining leaders**: Ensuring top-performing companies maintain their competitive AI advantages
3. **Cross-portfolio learning**: Facilitating knowledge transfer between portfolio companies on AI best practices

We remain confident in the fund's ability to generate superior returns through systematic AI-readiness improvement.

Sincerely,

*{gp_name} Management Team*

---

*This letter was generated by the PE Org-AI-R Agentic Platform. All data sourced from CS1-CS4.*
"""
        return letter


# Module-level singleton
lp_letter_generator = LPLetterGenerator()
