"""
Technology stack signal collector.

Case Study 2: Analyzes company technology stacks to detect
AI-related technologies (cloud ML, ML frameworks, data platforms, AI APIs).

For the 10 target companies, we use publicly known technology information
sourced from job postings, press releases, and engineering blogs.
BuiltWith/SimilarTech require paid API keys, so we use a research-based
approach with known data for the target companies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Union
from uuid import UUID

from rapidfuzz import fuzz

from app.models.signal import ExternalSignal, SignalCategory, SignalSource

logger = logging.getLogger(__name__)


@dataclass
class TechnologyDetection:
    """A detected technology."""

    name: str
    category: str
    is_ai_related: bool
    confidence: float


class TechStackCollector:
    """Analyze company technology stacks."""

    AI_TECHNOLOGIES = {
        # Cloud AI Services
        "aws sagemaker": "cloud_ml",
        "azure ml": "cloud_ml",
        "google vertex": "cloud_ml",
        "databricks": "cloud_ml",
        # ML Frameworks
        "tensorflow": "ml_framework",
        "pytorch": "ml_framework",
        "scikit-learn": "ml_framework",
        # Data Infrastructure
        "snowflake": "data_platform",
        "spark": "data_platform",
        # AI APIs
        "openai": "ai_api",
        "anthropic": "ai_api",
        "huggingface": "ai_api",
    }

    # Research-based known technology stacks for the 10 target companies.
    # Sources: public job postings, engineering blogs, press releases,
    # AWS/Azure/GCP customer case studies (all publicly available).
    KNOWN_TECH_STACKS: dict[str, list[dict]] = {
        "CAT": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "tableau", "category": "analytics", "ai": False},
        ],
        "DE": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "tensorflow", "category": "ml_framework", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "snowflake", "category": "data_platform", "ai": True},
        ],
        "UNH": [
            {"name": "azure ml", "category": "cloud_ml", "ai": True},
            {"name": "databricks", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
        ],
        "HCA": [
            {"name": "azure ml", "category": "cloud_ml", "ai": True},
            {"name": "snowflake", "category": "data_platform", "ai": True},
        ],
        "ADP": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "scikit-learn", "category": "ml_framework", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "openai", "category": "ai_api", "ai": True},
        ],
        "PAYX": [
            {"name": "azure ml", "category": "cloud_ml", "ai": True},
            {"name": "snowflake", "category": "data_platform", "ai": True},
        ],
        "WMT": [
            {"name": "azure ml", "category": "cloud_ml", "ai": True},
            {"name": "databricks", "category": "cloud_ml", "ai": True},
            {"name": "pytorch", "category": "ml_framework", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "openai", "category": "ai_api", "ai": True},
        ],
        "TGT": [
            {"name": "google vertex", "category": "cloud_ml", "ai": True},
            {"name": "snowflake", "category": "data_platform", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
        ],
        "JPM": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "pytorch", "category": "ml_framework", "ai": True},
            {"name": "tensorflow", "category": "ml_framework", "ai": True},
            {"name": "databricks", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "openai", "category": "ai_api", "ai": True},
            {"name": "huggingface", "category": "ai_api", "ai": True},
        ],
        "GS": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "pytorch", "category": "ml_framework", "ai": True},
            {"name": "databricks", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "openai", "category": "ai_api", "ai": True},
        ],
        # CS3 additional companies
        "NVDA": [
            {"name": "pytorch", "category": "ml_framework", "ai": True},
            {"name": "tensorflow", "category": "ml_framework", "ai": True},
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "databricks", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "openai", "category": "ai_api", "ai": True},
            {"name": "huggingface", "category": "ai_api", "ai": True},
        ],
        "GE": [
            {"name": "aws sagemaker", "category": "cloud_ml", "ai": True},
            {"name": "spark", "category": "data_platform", "ai": True},
            {"name": "snowflake", "category": "data_platform", "ai": True},
        ],
        "DG": [
            {"name": "snowflake", "category": "data_platform", "ai": True},
        ],
    }

    def get_known_technologies(self, ticker: str) -> list[TechnologyDetection]:
        """
        Get known technologies for a target company.

        This uses publicly sourced information from job postings,
        engineering blogs, and cloud vendor case studies.
        """
        stack = self.KNOWN_TECH_STACKS.get(ticker, [])
        techs = []
        for entry in stack:
            techs.append(
                TechnologyDetection(
                    name=entry["name"],
                    category=entry["category"],
                    is_ai_related=entry["ai"],
                    confidence=0.80,  # Known from public sources
                )
            )
        logger.info(f"Loaded {len(techs)} known technologies for {ticker}")
        return techs

    def detect_from_text(self, text: str) -> list[TechnologyDetection]:
        """
        Detect AI technologies mentioned in text (e.g., job descriptions,
        SEC filings, press releases) using fuzzy matching via rapidfuzz.
        """
        text_lower = text.lower()
        detected = []
        seen = set()

        for tech_name, category in self.AI_TECHNOLOGIES.items():
            # Exact substring match first
            if tech_name in text_lower and tech_name not in seen:
                detected.append(
                    TechnologyDetection(
                        name=tech_name,
                        category=category,
                        is_ai_related=True,
                        confidence=0.95,
                    )
                )
                seen.add(tech_name)
                continue

            # Fuzzy match for slight variations (e.g., "SageMaker" vs "sagemaker")
            for word in text_lower.split():
                if tech_name not in seen and fuzz.ratio(tech_name, word) > 85:
                    detected.append(
                        TechnologyDetection(
                            name=tech_name,
                            category=category,
                            is_ai_related=True,
                            confidence=0.75,
                        )
                    )
                    seen.add(tech_name)
                    break

        return detected

    def analyze_tech_stack(
        self, company_id: Union[UUID, str], technologies: list[TechnologyDetection]
    ) -> ExternalSignal:
        """Analyze technology stack for AI capabilities."""
        ai_techs = [t for t in technologies if t.is_ai_related]

        # Score by category
        categories_found = set(t.category for t in ai_techs)

        # Scoring:
        # - Each AI technology: 10 points (max 50)
        # - Each category covered: 12.5 points (max 50)
        tech_score = min(len(ai_techs) * 10, 50)
        category_score = min(len(categories_found) * 12.5, 50)

        score = tech_score + category_score

        return ExternalSignal(
            company_id=company_id,
            category=SignalCategory.DIGITAL_PRESENCE,
            source=SignalSource.BUILTWITH,
            signal_date=datetime.now(timezone.utc),
            raw_value=f"{len(ai_techs)} AI technologies detected",
            normalized_score=round(score, 1),
            confidence=0.85,
            metadata={
                "ai_technologies": [t.name for t in ai_techs],
                "categories": list(categories_found),
                "total_technologies": len(technologies),
            },
        )
