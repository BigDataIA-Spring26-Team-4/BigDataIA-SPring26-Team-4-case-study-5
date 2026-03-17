"""
Configuration management for PE Org-AI-R Platform.

This module uses pydantic-settings for robust environment variable management.
All configuration is validated at startup, ensuring the application fails fast
if required settings are missing or invalid.
"""

from typing import Optional
from pydantic import Field, field_validator, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    The Settings class provides type-safe access to all configuration values.
    Values are loaded from:
    1. Environment variables
    2. .env file (if present)
    3. Default values (where specified)
    
    The application will fail to start if required settings are missing.
    """
    
    # ========================================================================
    # Application Settings
    # ========================================================================
    APP_NAME: str = "PE Org-AI-R Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    
    # ========================================================================
    # Snowflake Database Configuration
    # ========================================================================
    SNOWFLAKE_ACCOUNT: str = Field(
        ...,  # ... means required
        description="Snowflake account identifier (e.g., xy12345.us-east-1)"
    )
    SNOWFLAKE_USER: str = Field(
        ...,
        description="Snowflake username"
    )
    SNOWFLAKE_PASSWORD: SecretStr = Field(
        ...,
        description="Snowflake password (secured, not logged)"
    )
    SNOWFLAKE_DATABASE: str = Field(
        default="PE_ORG_AIR_DB",
        description="Snowflake database name"
    )
    SNOWFLAKE_SCHEMA: str = Field(
        default="PE_ORG_AIR_SCHEMA",
        description="Snowflake schema name"
    )
    SNOWFLAKE_WAREHOUSE: str = Field(
        default="PE_ORG_AIR_WH",
        description="Snowflake warehouse name"
    )
    SNOWFLAKE_ROLE: Optional[str] = Field(
        default=None,
        description="Snowflake role (optional)"
    )
    
    # ========================================================================
    # Redis Cache Configuration
    # ========================================================================
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis host address"
    )
    REDIS_PORT: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Redis port number"
    )
    REDIS_DB: int = Field(
        default=0,
        ge=0,
        le=15,
        description="Redis database number (0-15)"
    )
    REDIS_PASSWORD: Optional[SecretStr] = Field(
        default=None,
        description="Redis password (if authentication is enabled, secured)"
    )
    REDIS_ENABLED: bool = Field(
        default=True,
        description="Enable Redis caching"
    )
    
    # Cache TTL settings (in seconds)
    CACHE_TTL_COMPANY: int = Field(default=300, description="Company cache TTL (5 minutes)")
    CACHE_TTL_INDUSTRY: int = Field(default=3600, description="Industry cache TTL (1 hour)")
    CACHE_TTL_ASSESSMENT: int = Field(default=120, description="Assessment cache TTL (2 minutes)")
    CACHE_TTL_DIMENSION_WEIGHTS: int = Field(default=86400, description="Dimension weights cache TTL (24 hours)")
    
    # ========================================================================
    # AWS S3 Configuration
    # ========================================================================
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default=None,
        description="AWS access key ID (optional if using IAM roles)"
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None,
        description="AWS secret access key (optional if using IAM roles)"
    )
    AWS_REGION: str = Field(
        default="us-east-1",
        description="AWS region for S3 bucket"
    )
    S3_BUCKET_NAME: Optional[str] = Field(
        default=None,
        description="S3 bucket name for document storage"
    )
    S3_ENABLED: bool = Field(
        default=False,
        description="Enable S3 storage"
    )
    
    # ========================================================================
    # PatentSearch API Configuration
    # ========================================================================
    PATENTSVIEW_API_KEY: Optional[str] = Field(
        default=None,
        description="PatentSearch API key (free, request from patentsview.org)"
    )
    
    # ========================================================================
    # CS3: Glassdoor & Board Data API Configuration
    # ========================================================================
    WEXTRACTOR_TOKEN: Optional[str] = Field(
        default=None,
        description="Wextractor auth token for Glassdoor reviews API (preferred)"
    )
    RAPIDAPI_KEY: Optional[str] = Field(
        default=None,
        description="RapidAPI key for Real-Time Glassdoor Data API (fallback)"
    )
    SEC_API_KEY: Optional[str] = Field(
        default=None,
        description="sec-api.io API key for Directors & Board Members data"
    )
    GNEWS_API_KEY: Optional[str] = Field(
        default=None,
        description="GNews.io API key for news/press release collection (free: 100 req/day)"
    )
    
    # ========================================================================
    # API Configuration
    # ========================================================================
    API_V1_PREFIX: str = Field(
        default="/api/v1",
        description="API version 1 prefix"
    )
    PAGINATION_DEFAULT_PAGE_SIZE: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Default page size for paginated endpoints"
    )
    PAGINATION_MAX_PAGE_SIZE: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum allowed page size"
    )
    
    # ========================================================================
    # Logging Configuration
    # ========================================================================
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    
    # ========================================================================
    # Model Configuration
    # ========================================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )
    
    # ========================================================================
    # Validators
    # ========================================================================
    
    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper
    
    @field_validator("SNOWFLAKE_ACCOUNT")
    @classmethod
    def validate_snowflake_account(cls, v: str) -> str:
        """Validate Snowflake account identifier format."""
        if not v or len(v) < 3:
            raise ValueError("SNOWFLAKE_ACCOUNT must be a valid account identifier")
        return v.strip()
    
    # ========================================================================
    # Computed Properties
    # ========================================================================
    
    @property
    def redis_connection_string(self) -> str:
        """
        Generate Redis connection string.
        
        Returns:
            str: Redis connection URL
        """
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# ============================================================================
# Global Settings Instance
# ============================================================================

# This will be imported throughout the application
# It will raise ValidationError if required settings are missing
settings = Settings()


# ============================================================================
# Helper Functions
# ============================================================================

def get_settings() -> Settings:
    """
    Dependency injection function for FastAPI.
    
    Returns:
        Settings: Application settings instance
        
    Example:
        @app.get("/config")
        def show_config(settings: Settings = Depends(get_settings)):
            return {"app_name": settings.APP_NAME}
    """
    return settings
