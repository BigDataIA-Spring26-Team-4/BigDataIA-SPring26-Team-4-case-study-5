"""
Bonus Extension: Investment Tracker with ROI (+5 pts).

Tracks entry and exit Org-AI-R scores for portfolio companies,
calculates AI-readiness improvement ROI, and monitors
value creation progress over the hold period.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


@dataclass
class InvestmentRecord:
    """Single portfolio investment with AI-readiness tracking."""
    company_id: str
    ticker: str
    entry_date: datetime
    entry_org_air: float
    entry_vr: float
    entry_hr: float
    current_org_air: float = 0.0
    current_vr: float = 0.0
    current_hr: float = 0.0
    exit_date: Optional[datetime] = None
    exit_org_air: Optional[float] = None
    target_org_air: float = 75.0
    investment_k: float = 500.0  # $K invested in AI initiatives
    ebitda_baseline_mm: float = 100.0  # Baseline EBITDA in $MM


@dataclass
class ROIMetrics:
    """ROI calculation result for an investment."""
    company_id: str
    hold_period_days: int
    org_air_improvement: float
    org_air_improvement_pct: float
    target_progress_pct: float      # % of way to target
    estimated_ebitda_uplift_mm: float
    investment_k: float
    roi_multiple: float             # EBITDA uplift / investment
    annualized_improvement: float   # Org-AI-R points per year
    status: str                     # "on_track", "ahead", "behind"


class InvestmentTracker:
    """
    Tracks portfolio investments and calculates AI-readiness ROI.

    Maintains entry/current scores and computes:
      - Org-AI-R improvement (absolute and %)
      - Progress toward target score
      - Estimated EBITDA uplift
      - ROI multiple (uplift / investment)
      - Annualized improvement rate
    """

    def __init__(self):
        self._investments: Dict[str, InvestmentRecord] = {}

    def record_entry(
        self,
        company_id: str,
        ticker: str,
        entry_org_air: float,
        entry_vr: float,
        entry_hr: float,
        target_org_air: float = 75.0,
        investment_k: float = 500.0,
        ebitda_baseline_mm: float = 100.0,
        entry_date: Optional[datetime] = None,
    ) -> InvestmentRecord:
        """Record a new portfolio entry with baseline scores."""
        record = InvestmentRecord(
            company_id=company_id.upper(),
            ticker=ticker.upper(),
            entry_date=entry_date or datetime.utcnow(),
            entry_org_air=entry_org_air,
            entry_vr=entry_vr,
            entry_hr=entry_hr,
            current_org_air=entry_org_air,
            current_vr=entry_vr,
            current_hr=entry_hr,
            target_org_air=target_org_air,
            investment_k=investment_k,
            ebitda_baseline_mm=ebitda_baseline_mm,
        )
        self._investments[company_id.upper()] = record
        logger.info("investment_entry_recorded", company_id=company_id, entry_score=entry_org_air)
        return record

    def update_current(
        self,
        company_id: str,
        current_org_air: float,
        current_vr: float,
        current_hr: float,
    ) -> InvestmentRecord:
        """Update current scores for a tracked investment."""
        ticker = company_id.upper()
        if ticker not in self._investments:
            raise ValueError(f"No investment record for {ticker}")

        record = self._investments[ticker]
        record.current_org_air = current_org_air
        record.current_vr = current_vr
        record.current_hr = current_hr

        logger.info("investment_updated", company_id=ticker, current_score=current_org_air)
        return record

    def record_exit(
        self,
        company_id: str,
        exit_org_air: float,
        exit_date: Optional[datetime] = None,
    ) -> InvestmentRecord:
        """Record portfolio exit with final scores."""
        ticker = company_id.upper()
        if ticker not in self._investments:
            raise ValueError(f"No investment record for {ticker}")

        record = self._investments[ticker]
        record.exit_date = exit_date or datetime.utcnow()
        record.exit_org_air = exit_org_air
        record.current_org_air = exit_org_air

        logger.info("investment_exit_recorded", company_id=ticker, exit_score=exit_org_air)
        return record

    def calculate_roi(self, company_id: str) -> ROIMetrics:
        """
        Calculate ROI metrics for an investment.

        EBITDA uplift estimate: each point of Org-AI-R improvement
        contributes ~0.25% EBITDA uplift (simplified v2.0 model).
        """
        ticker = company_id.upper()
        if ticker not in self._investments:
            raise ValueError(f"No investment record for {ticker}")

        record = self._investments[ticker]
        end_date = record.exit_date or datetime.utcnow()
        hold_days = max(1, (end_date - record.entry_date).days)

        improvement = record.current_org_air - record.entry_org_air
        improvement_pct = (
            (improvement / record.entry_org_air * 100)
            if record.entry_org_air > 0 else 0.0
        )

        # Progress toward target
        target_gap = record.target_org_air - record.entry_org_air
        target_progress = (
            (improvement / target_gap * 100) if target_gap > 0 else 100.0
        )

        # EBITDA uplift: ~0.25% per Org-AI-R point
        ebitda_uplift_pct = improvement * 0.25 / 100.0
        ebitda_uplift_mm = record.ebitda_baseline_mm * ebitda_uplift_pct

        # ROI multiple
        roi_multiple = (
            (ebitda_uplift_mm * 1000) / record.investment_k
            if record.investment_k > 0 else 0.0
        )

        # Annualized improvement
        annualized = improvement * (365.0 / hold_days)

        # Status
        expected_progress = min(100, hold_days / 365 * 100)  # assume 1yr plan
        if target_progress >= expected_progress * 1.2:
            status = "ahead"
        elif target_progress >= expected_progress * 0.8:
            status = "on_track"
        else:
            status = "behind"

        return ROIMetrics(
            company_id=ticker,
            hold_period_days=hold_days,
            org_air_improvement=round(improvement, 1),
            org_air_improvement_pct=round(improvement_pct, 1),
            target_progress_pct=round(min(target_progress, 100), 1),
            estimated_ebitda_uplift_mm=round(ebitda_uplift_mm, 2),
            investment_k=record.investment_k,
            roi_multiple=round(roi_multiple, 2),
            annualized_improvement=round(annualized, 1),
            status=status,
        )

    def get_portfolio_roi(self) -> List[ROIMetrics]:
        """Calculate ROI for all tracked investments."""
        return [
            self.calculate_roi(company_id)
            for company_id in self._investments
        ]

    def get_investment(self, company_id: str) -> Optional[InvestmentRecord]:
        """Get investment record for a company."""
        return self._investments.get(company_id.upper())


# Module-level singleton
investment_tracker = InvestmentTracker()
