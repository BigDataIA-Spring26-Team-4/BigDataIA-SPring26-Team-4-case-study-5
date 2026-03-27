from src.services.tracking.assessment_history import assessment_history_service

score_1 = {
    "org_air_score": 72.5,
    "vr_score": 68.0,
    "hr_score": 80.0,
    "synergy_score": 55.0,
    "dimension_scores": {
        "data_infrastructure": {"score": 75},
        "ai_governance": {"score": 65},
    },
    "confidence_interval": [68.0, 77.0],
}

score_2 = {
    "org_air_score": 78.91,
    "vr_score": 74.55,
    "hr_score": 91.46,
    "synergy_score": 61.24,
    "dimension_scores": {
        "data_infrastructure": {"score": 93.69},
        "ai_governance": {"score": 75.49},
    },
    "confidence_interval": [75.97, 81.85],
}

print("=== RECORD 1 ===")
print(assessment_history_service.record_assessment("NVDA", score_1, evidence_count=12))

print("\n=== RECORD 2 ===")
print(assessment_history_service.record_assessment("NVDA", score_2, evidence_count=25))

print("\n=== HISTORY ===")
print(assessment_history_service.get_history("NVDA"))

print("\n=== LATEST ===")
print(assessment_history_service.get_latest("NVDA"))

print("\n=== TREND ===")
print(assessment_history_service.calculate_trend("NVDA"))