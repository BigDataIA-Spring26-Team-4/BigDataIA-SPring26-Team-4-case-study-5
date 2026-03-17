"""
API routers package for PE Org-AI-R Platform.
"""

from app.routers import health, companies, assessments, scores, industries, config
# CS2: Evidence Collection routers
from app.routers import documents, signals
# Pipeline execution router
from app.routers import pipeline
# CS4: RAG & Search routers
from app.routers import search, justification

__all__ = [
    "health", "companies", "assessments", "scores", "industries", "config",
    "documents", "signals", "pipeline",
    "search", "justification",
]
