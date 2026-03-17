"""
Redis caching service for PE Org-AI-R Platform.

This module provides caching functionality using Redis with:
- Connection pooling
- Automatic serialization/deserialization
- TTL support
- Pattern-based invalidation
"""

import json
from typing import Optional, TypeVar, Type
from functools import wraps

import structlog
import redis
from pydantic import BaseModel

from app.config import settings

log = structlog.get_logger(__name__)

T = TypeVar('T', bound=BaseModel)

# ============================================================================
# Redis Client Setup
# ============================================================================

# Global Redis client (connection pool)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get Redis client with connection pooling.
    
    Returns:
        Redis client or None if Redis is disabled
    """
    global _redis_client
    
    if not settings.REDIS_ENABLED:
        log.debug("redis_disabled")
        return None
    
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD.get_secret_value() if settings.REDIS_PASSWORD else None,
                decode_responses=True,  # Automatically decode bytes to str
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            # Test connection
            _redis_client.ping()
            log.info(
                "redis_connected",
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB
            )
        except Exception as e:
            log.error("redis_connection_failed", error=str(e))
            _redis_client = None
    
    return _redis_client


# ============================================================================
# Cache Operations
# ============================================================================

def cache_key(prefix: str, *args, **kwargs) -> str:
    """
    Generate cache key from prefix and arguments.
    
    Args:
        prefix: Cache key prefix
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key
        
    Returns:
        Cache key string
        
    Example:
        >>> cache_key("company", "123")
        "company:123"
        >>> cache_key("assessment", company_id="456", type="screening")
        "assessment:company_id=456:type=screening"
    """
    parts = [prefix]
    
    # Add positional args
    for arg in args:
        if hasattr(arg, 'hex'):  # UUID
            parts.append(str(arg))
        else:
            parts.append(str(arg))
    
    # Add keyword args (sorted for consistency)
    for key in sorted(kwargs.keys()):
        value = kwargs[key]
        if value is not None:
            parts.append(f"{key}={value}")
    
    return ":".join(parts)


def get_cached(key: str, model: Type[T]) -> Optional[T]:
    """
    Get item from cache and deserialize to Pydantic model.
    
    Args:
        key: Cache key
        model: Pydantic model class
        
    Returns:
        Pydantic model instance or None
    """
    client = get_redis_client()
    if not client:
        return None
    
    try:
        data = client.get(key)
        if data:
            log.debug("cache_hit", key=key)
            return model.model_validate_json(data)
        log.debug("cache_miss", key=key)
        return None
    except Exception as e:
        log.warning("cache_get_error", key=key, error=str(e))
        return None


def set_cached(key: str, value: BaseModel, ttl: int) -> bool:
    """
    Cache Pydantic model with TTL.
    
    Args:
        key: Cache key
        value: Pydantic model to cache
        ttl: Time-to-live in seconds
        
    Returns:
        True if successful, False otherwise
    """
    client = get_redis_client()
    if not client:
        return False
    
    try:
        client.setex(
            key,
            ttl,
            value.model_dump_json()
        )
        log.debug("cache_set", key=key, ttl=ttl)
        return True
    except Exception as e:
        log.warning("cache_set_error", key=key, error=str(e))
        return False


def invalidate_cache(pattern: str) -> int:
    """
    Invalidate all cache entries matching pattern.
    
    Args:
        pattern: Redis key pattern (supports wildcards)
        
    Returns:
        Number of keys deleted
        
    Example:
        >>> invalidate_cache("company:*")  # Delete all company cache
        >>> invalidate_cache("assessment:123:*")  # Delete specific assessment cache
    """
    client = get_redis_client()
    if not client:
        return 0
    
    try:
        keys = list(client.scan_iter(match=pattern))
        if keys:
            deleted = client.delete(*keys)
            log.info("cache_invalidated", pattern=pattern, deleted=deleted)
            return deleted
        return 0
    except Exception as e:
        log.warning("cache_invalidate_error", pattern=pattern, error=str(e))
        return 0


# ============================================================================
# Decorator for Caching
# ============================================================================

def cached(prefix: str, ttl: Optional[int] = None):
    """
    Decorator to cache function results.
    
    Args:
        prefix: Cache key prefix
        ttl: Time-to-live in seconds (uses default from settings if None)
        
    Example:
        @cached(prefix="company", ttl=300)
        def get_company(db, company_id):
            return db.query(Company).filter_by(id=company_id).first()
    """
    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            # Skip first arg if it's 'db' (database session)
            cache_args = args[1:] if args and hasattr(args[0], 'query') else args
            
            # Remove 'db' from kwargs if present (from Depends(get_db))
            cache_kwargs = {k: v for k, v in kwargs.items() if k != 'db'}
            
            key = cache_key(prefix, *cache_args, **cache_kwargs)
            
            # Try to get from cache
            client = get_redis_client()
            if client:
                try:
                    cached_data = client.get(key)
                    if cached_data:
                        log.info("cache_hit", key=key, function=func.__name__)  # Changed to info to see it
                        # Return raw data (will be serialized by FastAPI)
                        return json.loads(cached_data)
                except Exception as e:
                    log.warning("cache_error", error=str(e))
            
            # Cache miss - execute function
            log.info("cache_miss", key=key, function=func.__name__)  # Changed to info to see it
            result = func(*args, **kwargs)
            
            # Cache the result
            if client and result is not None:
                try:
                    # Determine TTL
                    cache_ttl = ttl or settings.CACHE_TTL_COMPANY
                    
                    # Helper function to convert SQLAlchemy models to dict
                    def to_dict(obj):
                        # Check if it's a SQLAlchemy model (has __table__ attribute)
                        if hasattr(obj, '__table__'):
                            # Convert SQLAlchemy model to dict
                            return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
                        # Check if it's a Pydantic model
                        elif hasattr(obj, 'model_dump'):
                            return obj.model_dump()
                        else:
                            return obj
                    
                    # Serialize result
                    if isinstance(result, list):
                        # List of models (Pydantic or SQLAlchemy)
                        serialized = json.dumps([to_dict(item) for item in result], default=str)
                    elif hasattr(result, 'model_dump'):
                        # Single Pydantic model
                        serialized = result.model_dump_json()
                    elif hasattr(result, '__table__'):
                        # Single SQLAlchemy model
                        serialized = json.dumps(to_dict(result), default=str)
                    else:
                        # Raw data
                        serialized = json.dumps(result, default=str)
                    
                    client.setex(key, cache_ttl, serialized)
                    log.info("cache_stored", key=key, ttl=cache_ttl)  # Changed to info to see it
                except Exception as e:
                    log.warning("cache_store_error", error=str(e), key=key)
            
            return result
        
        return sync_wrapper
    return decorator


def invalidate(prefix: str):
    """
    Invalidate all cache entries with given prefix.
    
    Args:
        prefix: Cache key prefix
        
    Example:
        invalidate("company")  # Clear all company cache
    """
    pattern = f"{prefix}*"
    return invalidate_cache(pattern)


# ============================================================================
# Cache Statistics (Optional - for monitoring)
# ============================================================================

def get_cache_stats() -> dict:
    """
    Get cache statistics.
    
    Returns:
        Dictionary with cache stats
    """
    client = get_redis_client()
    if not client:
        return {"enabled": False}
    
    try:
        info = client.info()
        return {
            "enabled": True,
            "connected": True,
            "used_memory": info.get("used_memory_human"),
            "total_keys": client.dbsize(),
            "hits": info.get("keyspace_hits", 0),
            "misses": info.get("keyspace_misses", 0),
        }
    except Exception as e:
        log.error("cache_stats_error", error=str(e))
        return {
            "enabled": True,
            "connected": False,
            "error": str(e)
        }
