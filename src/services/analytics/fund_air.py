from typing import List


class FundAIRCalculator:
    def __init__(self, threshold: float = 60.0):
        self.threshold = threshold

    def calculate(self, portfolio: List[dict]) -> dict:
        if not portfolio:
            return {
                "fund_air": 0.0,
                "avg_score": 0.0,
                "pct_above_threshold": 0.0,
                "count": 0
            }

        scores = [p["org_air"] for p in portfolio if p["org_air"] > 0]

        if not scores:
            return {
                "fund_air": 0.0,
                "avg_score": 0.0,
                "pct_above_threshold": 0.0,
                "count": len(portfolio)
            }

        avg_score = sum(scores) / len(scores)

        above = [s for s in scores if s >= self.threshold]
        pct_above = (len(above) / len(scores)) * 100

        fund_air = (0.7 * avg_score) + (0.3 * pct_above)

        return {
            "fund_air": round(fund_air, 2),
            "avg_score": round(avg_score, 2),
            "pct_above_threshold": round(pct_above, 2),
            "count": len(scores)
        }