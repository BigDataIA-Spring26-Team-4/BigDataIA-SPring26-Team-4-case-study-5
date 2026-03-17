"""
Talent Concentration Calculator.

CS3 Task 5.0e: Measures key-person risk — how much AI capability
depends on a few individuals.

TC = 0.0 → distributed capability (low risk)
TC = 1.0 → single-person dependency (maximum risk)

TalentRiskAdj = 1 - 0.15 * max(0, TC - 0.25)
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Set
import math


SENIOR_KEYWORDS = ["principal", "staff", "director", "vp", "head", "chief", "fellow"]
MID_KEYWORDS = ["senior", "lead", "manager", "sr."]
ENTRY_KEYWORDS = ["junior", "associate", "entry", "intern", "jr."]


@dataclass
class JobAnalysis:
    total_ai_jobs: int
    senior_ai_jobs: int
    mid_ai_jobs: int
    entry_ai_jobs: int
    unique_skills: Set[str]


class TalentConcentrationCalculator:
    """
    TC = 0.4 * leadership_ratio + 0.3 * team_size_factor
       + 0.2 * skill_concentration + 0.1 * individual_mentions

    Bounded to [0, 1].
    """

    def calculate_tc(
        self,
        job_analysis: JobAnalysis,
        glassdoor_individual_mentions: int = 0,
        glassdoor_review_count: int = 1,
    ) -> Decimal:
        # leadership ratio
        if job_analysis.total_ai_jobs > 0:
            leadership_ratio = job_analysis.senior_ai_jobs / job_analysis.total_ai_jobs
        else:
            leadership_ratio = 0.5

        # team size factor — smaller team = higher concentration
        if job_analysis.total_ai_jobs > 0:
            team_size_factor = min(1.0, 1.0 / (math.sqrt(job_analysis.total_ai_jobs) + 0.1))
        else:
            team_size_factor = 0.8

        # skill concentration — fewer unique skills = higher concentration
        skill_concentration = max(0, 1 - len(job_analysis.unique_skills) / 15)

        # individual mention factor
        if glassdoor_review_count > 0:
            individual_factor = min(1.0, glassdoor_individual_mentions / glassdoor_review_count)
        else:
            individual_factor = 0.5

        tc = (
            0.4 * leadership_ratio
            + 0.3 * team_size_factor
            + 0.2 * skill_concentration
            + 0.1 * individual_factor
        )

        tc = max(0, min(1, tc))
        return Decimal(str(tc)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def analyze_job_postings(self, postings: List[dict]) -> JobAnalysis:
        total = 0
        senior = 0
        mid = 0
        entry = 0
        skills: Set[str] = set()

        for p in postings:
            title = str(p.get("title", "")).lower()
            description = str(p.get("description", "")).lower()
            is_ai = p.get("is_ai_related", False)

            if not is_ai:
                continue

            total += 1

            if any(kw in title for kw in SENIOR_KEYWORDS):
                senior += 1
            elif any(kw in title for kw in MID_KEYWORDS):
                mid += 1
            elif any(kw in title for kw in ENTRY_KEYWORDS):
                entry += 1
            else:
                mid += 1  # default to mid-level

            # extract skills from description
            ai_skills = [
                "python", "pytorch", "tensorflow", "scikit-learn",
                "spark", "kubernetes", "docker", "aws", "azure", "gcp",
                "sagemaker", "mlflow", "huggingface", "langchain", "openai",
            ]
            for sk in ai_skills:
                if sk in description:
                    skills.add(sk)

        return JobAnalysis(
            total_ai_jobs=total,
            senior_ai_jobs=senior,
            mid_ai_jobs=mid,
            entry_ai_jobs=entry,
            unique_skills=skills,
        )
