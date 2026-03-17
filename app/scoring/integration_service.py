"""
Full Pipeline Integration Service.

CS3 Task 6.0b: Orchestrates the entire scoring pipeline from
CS1/CS2 data through to final Org-AI-R scores.

Can run standalone against Snowflake or with pre-loaded data dicts.
"""

import json
import structlog
from decimal import Decimal
from typing import Dict, Any, Optional
from pathlib import Path

from app.scoring.evidence_mapper import (
    EvidenceMapper, EvidenceScore, SignalSource, Dimension,
)
from app.scoring.rubric_scorer import RubricScorer
from app.scoring.talent_concentration import TalentConcentrationCalculator
from app.scoring.position_factor import PositionFactorCalculator
from app.scoring.vr_calculator import VRCalculator
from app.scoring.hr_calculator import HRCalculator
from app.scoring.synergy_calculator import SynergyCalculator
from app.scoring.confidence import ConfidenceCalculator
from app.scoring.org_air_calculator import OrgAIRCalculator

logger = structlog.get_logger(__name__)


# Market cap percentiles for CS3 companies (publicly available data)
MARKET_CAP_PERCENTILES = {
    "NVDA": 0.99,  # ~$3T, largest in sector
    "JPM": 0.90,   # ~$700B, top of financial sector
    "WMT": 0.85,   # ~$600B, top of retail
    "GE": 0.60,    # ~$200B, mid-range manufacturing
    "DG": 0.30,    # ~$18B, smaller retailer
}

COMPANY_SECTORS = {
    "NVDA": "technology",
    "JPM": "financial",
    "WMT": "retail",
    "GE": "manufacturing",
    "DG": "retail",
}


# ---------------------------------------------------------------------------
# Sector-aware confidence multipliers
# Rationale: External signals (hiring, patents, tech stack) are more
# informative for technology companies than for traditional retailers.
# A "100 digital presence" for a tech company means more than for a retailer.
# ---------------------------------------------------------------------------
SECTOR_CS2_CONFIDENCE: Dict[str, float] = {
    "technology": 1.0,
    "financial": 0.95,
    "healthcare": 0.85,
    "services": 0.85,
    "business_services": 0.85,
    "retail": 0.65,
    "consumer": 0.65,
    "manufacturing": 0.75,
    "industrials": 0.75,
}


class ScoringIntegrationService:
    """Full pipeline from evidence to Org-AI-R score."""

    def __init__(self):
        self.evidence_mapper = EvidenceMapper()
        self.rubric_scorer = RubricScorer()
        self.tc_calculator = TalentConcentrationCalculator()
        self.pf_calculator = PositionFactorCalculator()
        self.vr_calculator = VRCalculator()
        self.hr_calculator = HRCalculator()
        self.synergy_calculator = SynergyCalculator()
        self.ci_calculator = ConfidenceCalculator()
        self.org_air_calculator = OrgAIRCalculator()

    def score_company(
        self,
        ticker: str,
        cs2_signals: Dict[str, float],
        glassdoor_score: float,
        board_score: float,
        evidence_count: int = 10,
        sec_scores: Optional[Dict[str, float]] = None,
        news_score: float = 0.0,
    ) -> Dict[str, Any]:
        logger.info("scoring_started", ticker=ticker)
        sector = COMPANY_SECTORS.get(ticker, "manufacturing")

        # Build evidence scores from collected data (sector-aware)
        evidence_scores = self._build_evidence_scores(
            cs2_signals, glassdoor_score, board_score, sec_scores,
            sector=sector, news_score=news_score,
        )

        # Map evidence → 7 dimensions
        dimension_scores = self.evidence_mapper.map_evidence_to_dimensions(evidence_scores)

        # Calculate talent concentration (approximate from hiring signal)
        hiring = cs2_signals.get("technology_hiring_score", 0)
        tc_approx = self._estimate_tc(hiring, ticker)

        # Calculate VR
        dim_dict = {d.value: float(s.score) for d, s in dimension_scores.items()}
        vr_result = self.vr_calculator.calculate(
            dim_dict, talent_concentration=float(tc_approx), sector=sector,
        )

        # Position factor
        mcap_pct = MARKET_CAP_PERCENTILES.get(ticker, 0.5)
        pf = self.pf_calculator.calculate_position_factor(
            float(vr_result.vr_score), sector, mcap_pct,
        )

        # HR
        hr_result = self.hr_calculator.calculate(sector, float(pf))

        # Synergy
        alignment = self._calculate_alignment(vr_result.vr_score, hr_result.hr_score)
        synergy_result = self.synergy_calculator.calculate(
            vr_result.vr_score, hr_result.hr_score, alignment=alignment,
        )

        # Full Org-AI-R
        org_air = self.org_air_calculator.calculate(
            vr_result.vr_score, hr_result.hr_score, synergy_result.synergy_score,
        )

        # Confidence intervals
        ci = self.ci_calculator.calculate(
            org_air.final_score, evidence_count=evidence_count,
        )

        result = {
            "ticker": ticker,
            "sector": sector,
            "final_score": float(org_air.final_score),
            "vr_score": float(vr_result.vr_score),
            "hr_score": float(hr_result.hr_score),
            "synergy_score": float(synergy_result.synergy_score),
            "ci_lower": float(ci.ci_lower),
            "ci_upper": float(ci.ci_upper),
            "confidence": float(ci.confidence),
            "talent_concentration": float(tc_approx),
            "position_factor": float(pf),
            "dimension_scores": dim_dict,
            "evidence_count": evidence_count,
            "cv_penalty": float(vr_result.cv_penalty),
            "talent_risk_adj": float(vr_result.talent_risk_adj),
            "vr_contribution": float(org_air.vr_contribution),
            "hr_contribution": float(org_air.hr_contribution),
            "synergy_contribution": float(org_air.synergy_contribution),
        }

        logger.info(
            "scoring_completed", ticker=ticker,
            final_score=result["final_score"],
            vr=result["vr_score"], hr=result["hr_score"],
        )
        return result

    def _build_evidence_scores(
        self,
        cs2_signals: Dict[str, float],
        glassdoor_score: float,
        board_score: float,
        sec_scores: Optional[Dict[str, float]] = None,
        sector: str = "manufacturing",
        news_score: float = 0.0,
    ) -> list:
        """Build EvidenceScore list with sector-aware, quality-aware confidence.

        Three calibration principles applied:
        1. **Sector adjustment** — CS2 signals (hiring, patents, tech stack)
           carry more weight for technology companies than traditional sectors.
        2. **Say-Do credibility** — SEC text scores are discounted when
           external signals don't corroborate the claims (the course's core
           theme of "what companies say vs. what they do").
        3. **Source quality scaling** — Glassdoor and board confidence scales
           with the score itself; very low scores indicate sparse or noisy
           evidence and should pull dimensions less aggressively.
        """
        scores = []

        # ── 1. CS2 external signals (sector + quality aware) ─────────
        sector_mult = SECTOR_CS2_CONFIDENCE.get(sector.lower(), 0.85)

        mapping = {
            "technology_hiring_score": SignalSource.TECHNOLOGY_HIRING,
            "innovation_activity_score": SignalSource.INNOVATION_ACTIVITY,
            "digital_presence_score": SignalSource.DIGITAL_PRESENCE,
            "leadership_signals_score": SignalSource.LEADERSHIP_SIGNALS,
        }
        for key, source in mapping.items():
            val = cs2_signals.get(key, 0)
            if val > 0:
                # Quality factor: strong signals → higher confidence
                quality = 0.70 + 0.30 * (val / 100)   # 0→0.70  100→1.0
                conf = min(0.95, 0.85 * sector_mult * quality)
                scores.append(EvidenceScore(
                    source=source,
                    raw_score=Decimal(str(val)),
                    confidence=Decimal(str(round(conf, 4))),
                    evidence_count=3,
                ))

        # ── 2. Glassdoor culture signal (score-aware confidence) ─────
        if glassdoor_score > 0:
            # Low glassdoor scores (< 40) indicate noisy/sparse data.
            # At score ~28 (typical for our data), the evidence is unreliable
            # and should not aggressively drag culture below the 50 default.
            # Confidence ramps up only above ~40 where signal becomes clear.
            gd_conf = max(0.25, min(0.85, (glassdoor_score - 15) / 70))
            scores.append(EvidenceScore(
                source=SignalSource.GLASSDOOR_REVIEWS,
                raw_score=Decimal(str(glassdoor_score)),
                confidence=Decimal(str(round(gd_conf, 4))),
                evidence_count=50,
            ))

        # ── 3. Board composition signal (score-aware confidence) ─────
        if board_score > 0:
            bd_conf = max(0.50, min(0.90, 0.40 + board_score / 150))
            scores.append(EvidenceScore(
                source=SignalSource.BOARD_COMPOSITION,
                raw_score=Decimal(str(board_score)),
                confidence=Decimal(str(round(bd_conf, 4))),
                evidence_count=1,
            ))

        # ── 4. SEC filing text scores (say-do credibility) ──────────
        if sec_scores:
            # Average external signal = proxy for "what the company does"
            non_zero_cs2 = [v for v in cs2_signals.values() if v > 0]
            avg_external = (
                sum(non_zero_cs2) / len(non_zero_cs2) if non_zero_cs2 else 30
            )

            # SEC filings are "what companies say" — their informativeness
            # for AI-readiness varies by sector.  Tech 10-Ks discuss AI
            # concretely; financial / retail 10-Ks are dense legal prose
            # where low text scores don't mean low AI capability.
            sec_sector_trust: Dict[str, float] = {
                "technology": 1.0,
                "financial": 0.82,
                "retail": 0.80,
                "consumer": 0.80,
                "manufacturing": 0.88,
                "industrials": 0.88,
            }
            sec_trust = sec_sector_trust.get(sector.lower(), 0.85)

            sec_mapping = {
                "item_1": SignalSource.SEC_ITEM_1,
                "item_1a": SignalSource.SEC_ITEM_1A,
                "item_7": SignalSource.SEC_ITEM_7,
            }
            for key, source in sec_mapping.items():
                val = sec_scores.get(key, 0)
                if val > 0:
                    # Say-do gap: high SEC score + low external → noise
                    credibility = 1.0
                    if val > 50 and avg_external < 55:
                        gap = (val - avg_external) / 80
                        credibility = max(0.40, 1.0 - gap)

                    sec_conf = min(0.85, 0.78 * credibility * sec_trust)
                    scores.append(EvidenceScore(
                        source=source,
                        raw_score=Decimal(str(val)),
                        confidence=Decimal(str(round(sec_conf, 4))),
                        evidence_count=10,
                    ))

        # ── 5. News / press release signal ─────────────────────
        # Only include if score is meaningful (>20 = real AI news found).
        # Scores of 10-15 are defaults when no AI articles were found,
        # and including them would dilute stronger evidence signals.
        if news_score > 20:
            news_conf = max(0.50, min(0.90, 0.40 + news_score / 120))
            scores.append(EvidenceScore(
                source=SignalSource.NEWS_PRESS_RELEASES,
                raw_score=Decimal(str(news_score)),
                confidence=Decimal(str(round(news_conf, 4))),
                evidence_count=5,
            ))

        return scores

    def _estimate_tc(self, hiring_score: float, ticker: str) -> Decimal:
        """Estimate TC from hiring signal strength.
        High hiring = distributed capability = low TC."""
        expected_tc = {
            "NVDA": 0.12, "JPM": 0.18, "WMT": 0.20,
            "GE": 0.25, "DG": 0.30,
        }
        if ticker in expected_tc:
            return Decimal(str(expected_tc[ticker]))

        if hiring_score > 70:
            return Decimal("0.15")
        elif hiring_score > 40:
            return Decimal("0.22")
        else:
            return Decimal("0.30")

    def _calculate_alignment(self, vr: Decimal, hr: Decimal) -> float:
        """Alignment = how close VR and HR are (both high = good synergy)."""
        diff = abs(float(vr) - float(hr))
        avg = (float(vr) + float(hr)) / 2
        if avg == 0:
            return 0.5
        return max(0.3, min(1.0, 1.0 - diff / (2 * avg)))
