"""
Job posting signal collector for AI hiring evidence.

Case Study 2: Collects and analyzes job postings to determine
whether companies are actually hiring AI/ML talent (what they DO)
vs. just talking about AI (what they SAY).

Uses python-jobspy for scraping with built-in proxy rotation to
avoid IP bans. Falls back to simulated data if scraping fails.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID
from typing import Union

from app.models.signal import ExternalSignal, SignalCategory, SignalSource

logger = logging.getLogger(__name__)


@dataclass
class JobPosting:
    """Represents a job posting."""

    title: str
    company: str
    location: str
    description: str
    posted_date: str | None
    source: str
    url: str
    is_ai_related: bool
    ai_skills: list[str]


class JobSignalCollector:
    """Collect job posting signals for AI hiring."""

    AI_KEYWORDS = [
        "machine learning",
        "ml engineer",
        "data scientist",
        "artificial intelligence",
        "deep learning",
        "nlp",
        "computer vision",
        "mlops",
        "ai engineer",
        "pytorch",
        "tensorflow",
        "llm",
        "large language model",
        "generative ai",
        "gen ai",
        "ai/ml",
        "ml intern",
        "ai intern",
        "neural network",
        "data engineer",
    ]

    AI_SKILLS = [
        "python",
        "pytorch",
        "tensorflow",
        "scikit-learn",
        "spark",
        "hadoop",
        "kubernetes",
        "docker",
        "aws sagemaker",
        "azure ml",
        "gcp vertex",
        "huggingface",
        "langchain",
        "openai",
    ]

    def scrape_jobs(self, company_name: str, max_results: int = 25) -> list[JobPosting]:
        """
        Scrape real job postings using python-jobspy.

        python-jobspy handles proxy rotation and rate limiting internally,
        which protects against IP bans. We also add delays between requests.

        Falls back to empty list on failure (never crashes the pipeline).
        """
        try:
            from jobspy import scrape_jobs

            logger.info(f"Scraping jobs for '{company_name}' via python-jobspy...")

            # python-jobspy scrapes Indeed/LinkedIn/Glassdoor with built-in
            # proxy support and anti-ban measures
            df = scrape_jobs(
                site_name=["indeed"],  # Start with indeed only (least aggressive)
                search_term=f'"{company_name}" AI OR "machine learning" OR "data scientist"',
                results_wanted=max_results,
                country_indeed="USA",
                # python-jobspy uses proxies internally if available
                # Adding delay to be respectful
            )

            # Small delay to be respectful to the source
            time.sleep(2)

            postings = []
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    posting = JobPosting(
                        title=str(row.get("title", "")),
                        company=str(row.get("company_name", company_name)),
                        location=str(row.get("location", "Unknown")),
                        description=str(row.get("description", "")),
                        posted_date=str(row.get("date_posted", "")),
                        source="indeed",
                        url=str(row.get("job_url", "")),
                        is_ai_related=False,
                        ai_skills=[],
                    )
                    # Classify each posting
                    posting = self.classify_posting(posting)
                    postings.append(posting)

                logger.info(
                    f"Scraped {len(postings)} postings for {company_name}, "
                    f"{sum(1 for p in postings if p.is_ai_related)} AI-related"
                )
            else:
                logger.warning(f"No jobs found for {company_name}")

            return postings

        except ImportError:
            logger.warning(
                "python-jobspy not installed. Run: pip install python-jobspy. "
                "Falling back to empty postings."
            )
            return []
        except Exception as e:
            logger.error(f"Job scraping failed for {company_name}: {e}")
            logger.info("Falling back to empty postings (scoring will reflect zero)")
            return []

    def analyze_job_postings(
        self, company_id: Union[UUID, str], company: str, postings: list[JobPosting]
    ) -> ExternalSignal:
        """Analyze job postings to calculate hiring signal."""
        total_tech_jobs = len([p for p in postings if self._is_tech_job(p)])
        ai_jobs = len([p for p in postings if p.is_ai_related])

        # Calculate metrics
        if total_tech_jobs > 0:
            ai_ratio = ai_jobs / total_tech_jobs
        else:
            ai_ratio = 0

        # Collect all AI skills mentioned
        all_skills = set()
        for posting in postings:
            all_skills.update(posting.ai_skills)

        # Score calculation (0-100)
        # - Base: AI ratio * 60 (max 60 points)
        # - Skill diversity: len(skills) / 10 * 20 (max 20 points)
        # - Volume bonus: min(ai_jobs / 5, 1) * 20 (max 20 points)
        score = (
            min(ai_ratio * 60, 60)
            + min(len(all_skills) / 10, 1) * 20
            + min(ai_jobs / 5, 1) * 20
        )

        return ExternalSignal(
            company_id=company_id,
            category=SignalCategory.TECHNOLOGY_HIRING,
            source=SignalSource.INDEED,
            signal_date=datetime.now(timezone.utc),
            raw_value=f"{ai_jobs}/{total_tech_jobs} AI jobs",
            normalized_score=round(score, 1),
            confidence=min(0.5 + total_tech_jobs / 100, 0.95),
            metadata={
                "total_tech_jobs": total_tech_jobs,
                "ai_jobs": ai_jobs,
                "ai_ratio": round(ai_ratio, 3),
                "skills_found": list(all_skills),
                "total_postings_scraped": len(postings),
            },
        )

    def classify_posting(self, posting: JobPosting) -> JobPosting:
        """Classify a job posting as AI-related or not."""
        text = f"{posting.title} {posting.description}".lower()

        # Check for AI keywords
        is_ai = any(kw in text for kw in self.AI_KEYWORDS)

        # Extract AI skills
        skills = [skill for skill in self.AI_SKILLS if skill in text]

        posting.is_ai_related = is_ai
        posting.ai_skills = skills

        return posting

    def _is_tech_job(self, posting: JobPosting) -> bool:
        """Check if posting is a technology job."""
        tech_keywords = [
            "engineer",
            "developer",
            "programmer",
            "software",
            "data",
            "analyst",
            "scientist",
            "technical",
        ]
        title_lower = posting.title.lower()
        return any(kw in title_lower for kw in tech_keywords)
