"""
Complete Pipeline Exercise: Why did NVIDIA score high on Data Infrastructure?

Prerequisites: results/*.json files present (from CS3 scoring).
Optionally: CS1/CS2/CS3 APIs running for live data.

This exercise runs the full CS1→CS2→CS3→CS4 pipeline:
  1. Verify company in CS1 (local fallback)
  2. Fetch CS3 score for Data Infrastructure
  3. Get rubric for that level
  4. Index sample evidence in hybrid retriever
  5. Generate score justification
  6. Display complete results

Run with: python -m exercises.complete_pipeline
"""

import asyncio
import os
import sys
import tempfile

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def exercise_nvda_justification():
    """Generate score justification for NVIDIA Data Infrastructure."""

    # Use temp ChromaDB for this exercise
    tmpdir = tempfile.mkdtemp(prefix="cs4_exercise_")
    os.environ.setdefault("CS4_CHROMA_PERSIST_DIR", tmpdir)
    os.environ.setdefault("CS4_PRIMARY_MODEL", "")  # No LLM needed

    from src.config import CS4Settings
    from src.services.integration.cs1_client import CS1Client
    from src.services.integration.cs3_client import CS3Client, Dimension
    from src.services.llm.router import ModelRouter
    from src.services.search.vector_store import VectorStore
    from src.services.retrieval.hybrid import HybridRetriever
    from src.services.retrieval.dimension_mapper import DimensionMapper
    from src.services.justification.generator import JustificationGenerator

    settings = CS4Settings()

    print("=" * 60)
    print("EXERCISE: NVIDIA Data Infrastructure Score Justification")
    print("=" * 60)

    # Step 1: Verify company in CS1
    cs1 = CS1Client()
    company = cs1._load_from_local("NVDA")
    print(f"\n[CS1] Company: {company.name}")
    print(f"  Sector: {company.sector.value}")
    print(f"  Market Cap Percentile: {company.market_cap_percentile:.2f}")

    # Step 2: Fetch CS3 score
    cs3 = CS3Client()
    score = (await cs3.get_assessment("NVDA")).dimension_scores[Dimension.DATA_INFRASTRUCTURE]
    print(f"\n[CS3] Data Infrastructure Score: {score.score:.1f}")
    print(f"  Level: {score.level.value} ({score.level.name_label})")
    print(f"  95% CI: [{score.confidence_interval[0]:.1f}, {score.confidence_interval[1]:.1f}]")

    # Step 3: Get rubric for that level
    rubrics = await cs3.get_rubric(Dimension.DATA_INFRASTRUCTURE, score.level)
    rubric = rubrics[0] if rubrics else None
    if rubric:
        print(f"\n[CS3] Level {score.level.value} Rubric:")
        print(f"  {rubric.criteria_text[:100]}...")
        print(f"  Keywords: {rubric.keywords[:5]}")

    # Step 4: Index sample evidence
    retriever = HybridRetriever(settings, VectorStore(settings))
    mapper = DimensionMapper()

    sample_evidence = [
        {
            "doc_id": "nvda_di_sec_1",
            "content": (
                "NVIDIA operates a comprehensive Snowflake data lakehouse with "
                "real-time streaming pipelines, achieving 95% data quality. "
                "API-first data mesh architecture with automated data catalog."
            ),
            "metadata": {
                "company_id": "NVDA", "source_type": "sec_10k_item_1",
                "dimension": "data_infrastructure", "confidence": 0.9,
            },
        },
        {
            "doc_id": "nvda_di_sec_2",
            "content": (
                "Cloud migration to Azure and AWS hybrid cloud complete. "
                "Data warehouse modernization includes ETL pipelines and "
                "data lake integration for machine learning workflows."
            ),
            "metadata": {
                "company_id": "NVDA", "source_type": "sec_10k_item_7",
                "dimension": "data_infrastructure", "confidence": 0.85,
            },
        },
        {
            "doc_id": "nvda_talent_1",
            "content": (
                "Hiring 50 ML engineers and data scientists for AI platform. "
                "Active recruitment for large team leadership roles."
            ),
            "metadata": {
                "company_id": "NVDA", "source_type": "job_posting_linkedin",
                "dimension": "talent", "confidence": 0.85,
            },
        },
        {
            "doc_id": "nvda_tech_1",
            "content": (
                "SageMaker MLOps pipeline with feature store and model registry. "
                "Automated CI/CD for ML models with experiment tracking."
            ),
            "metadata": {
                "company_id": "NVDA", "source_type": "sec_10k_item_1",
                "dimension": "technology_stack", "confidence": 0.88,
            },
        },
    ]

    retriever.index_documents(sample_evidence)
    print(f"\n[CS4] Indexed {len(sample_evidence)} documents")

    # Step 5: Generate justification
    generator = JustificationGenerator(
        cs3=cs3, retriever=retriever,
        router=ModelRouter(settings), settings=settings,
    )
    justification = await generator.generate_justification(
        "NVDA", Dimension.DATA_INFRASTRUCTURE,
    )

    # Step 6: Display results
    print("\n" + "=" * 60)
    print("SCORE JUSTIFICATION")
    print("=" * 60)
    print(f"\nCompany: {company.name} ({company.ticker})")
    print(f"Dimension: Data Infrastructure")
    print(f"Score: {justification.score:.0f}/100 "
          f"(Level {justification.level} — {justification.level_name})")
    print(f"Confidence: [{justification.confidence_interval[0]:.0f}, "
          f"{justification.confidence_interval[1]:.0f}]")

    print(f"\nRubric Match:")
    print(f"  {justification.rubric_criteria[:200]}...")

    print(f"\nSupporting Evidence ({len(justification.supporting_evidence)} items):")
    for i, e in enumerate(justification.supporting_evidence, 1):
        print(f"  {i}. [{e.source_type}] (conf={e.confidence:.2f})")
        print(f"     {e.content[:100]}...")
        if e.matched_keywords:
            print(f"     Matched: {e.matched_keywords}")

    print(f"\nGaps Identified:")
    for gap in justification.gaps_identified:
        print(f"  — {gap}")

    print(f"\nEvidence Strength: {justification.evidence_strength.upper()}")

    print(f"\nGenerated Summary:")
    print(f"  {justification.generated_summary}")

    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 60)
    print("EXERCISE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(exercise_nvda_justification())
