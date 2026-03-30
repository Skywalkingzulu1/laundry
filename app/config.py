from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.
    Defaults are provided for local development but should be overridden in production
    via GitHub Secrets or a .env file.
    """
    SECRET_KEY: str = "supersecretkeychange_me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Instantiate a single settings object for import throughout the project
settings = Settings()
