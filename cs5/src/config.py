from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    CS1_URL: str = "http://localhost:8000"
    CS2_URL: str = "http://localhost:8000"
    CS3_URL: str = "http://localhost:8000"
    CS4_URL: str = "http://localhost:8003"

    model_config = {"env_file": ".env"}


settings = Settings()
