DUE_DILIGENCE_ASSESSMENT_PROMPT = """
You are conducting an AI due diligence assessment for a portfolio company.

Tasks:
1. Retrieve company evidence.
2. Calculate Org-AI-R score and dimension breakdown.
3. Generate score justifications for key dimensions.
4. Identify gaps and value creation opportunities.
5. Recommend follow-up items for investment committee review.

Return a concise but structured assessment.
""".strip()

IC_MEETING_PREP_PROMPT = """
Prepare an Investment Committee briefing package for the target company.

Include:
1. Org-AI-R score summary
2. Key dimension strengths and weaknesses
3. Supporting evidence
4. Main gaps and risks
5. Recommended value creation initiatives
6. Questions for IC discussion
""".strip()