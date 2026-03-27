from src.services.analytics.fund_air import FundAIRCalculator

portfolio = [
    {"org_air": 78.91},
    {"org_air": 66.13},
    {"org_air": 57.45},
    {"org_air": 0.0},
]

calc = FundAIRCalculator()

print(calc.calculate(portfolio))