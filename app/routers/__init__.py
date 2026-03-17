"""
API routers package for PE Org-AI-R Platform.
"""

from app.routers import health, companies, assessments, scores, industries, config
# CS2: Evidence Collection routers
from app.routers import documents, signals
# Pipeline execution router
from app.routers import pipeline

__all__ = [
    "health", "companies", "assessments", "scores", "industries", "config",
    "documents", "signals", "pipeline",
]
