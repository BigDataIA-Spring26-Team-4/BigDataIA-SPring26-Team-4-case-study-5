"""
Health check router for PE Org-AI-R Platform.

This endpoint checks the health of all system dependencies:
- Snowflake database connection
- Redis cache connection
- S3 storage (if enabled)
"""

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel
from typing import Dict
from datetime import datetime

from app.config import settings

log = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str
    dependencies: Dict[str, str]


async def check_snowflake() -> str:
    """
    Check Snowflake database connection.
    
    Returns:
        str: "healthy" if connection works, "unhealthy" otherwise
    """
    try:
        from app.services.snowflake import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        log.debug("snowflake_health_check", status="healthy")
        return "healthy"
    except Exception as e:
        log.error("snowflake_health_check_failed", error=str(e))
        return "unhealthy"


async def check_redis() -> str:
    """
    Check Redis connection.
    
    Returns:
        str: "healthy" if connection works, "unhealthy" or "disabled"
    """
    if not settings.REDIS_ENABLED:
        return "disabled"
    
    try:
        import redis
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD.get_secret_value() if settings.REDIS_PASSWORD else None,
            socket_connect_timeout=2,
        )
        r.ping()
        log.debug("redis_health_check", status="healthy")
        return "healthy"
    except Exception as e:
        log.error("redis_health_check_failed", error=str(e))
        return "unhealthy"


async def check_s3() -> str:
    """
    Check S3 connection.
    
    Returns:
        str: "healthy" if connection works, "unhealthy" or "disabled"
    """
    if not settings.S3_ENABLED:
        return "disabled"
    
    try:
        import boto3
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        # Just check if we can list buckets (lightweight operation)
        s3.list_buckets()
        log.debug("s3_health_check", status="healthy")
        return "healthy"
    except Exception as e:
        log.error("s3_health_check_failed", error=str(e))
        return "unhealthy"


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check health of all dependencies.
    
    Returns:
        HealthResponse: Status of the application and its dependencies
        
    Status Codes:
        - 200: All systems healthy
        - 503: One or more systems unhealthy
    """
    log.debug("health_check_started")
    
    dependencies = {
        "snowflake": await check_snowflake(),
        "redis": await check_redis(),
        "s3": await check_s3(),
    }
    
    # Determine overall health (ignore "disabled" services)
    active_deps = {k: v for k, v in dependencies.items() if v != "disabled"}
    all_healthy = all(v == "healthy" for v in active_deps.values())
    
    response = HealthResponse(
        status="healthy" if all_healthy else "degraded",
        timestamp=datetime.now(),
        version=settings.APP_VERSION,
        dependencies=dependencies
    )
    
    log.info(
        "health_check_completed",
        status=response.status,
        dependencies=dependencies
    )
    
    # Return 503 if any system is unhealthy
    if not all_healthy:
        return response
    
    return response
