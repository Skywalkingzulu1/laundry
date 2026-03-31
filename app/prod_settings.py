from pydantic_settings import BaseSettings, SettingsConfigDict


class ProdSettings(BaseSettings):
    """Production configuration loaded from environment variables and secret stores.

    This mirrors the development Settings but expects values to be provided via the
    environment (e.g., CI/CD secret injection, Docker secrets, or a .env file in the
    production container). No default values are supplied so missing variables will
    raise a validation error at startup, preventing the application from running with
    insecure defaults.
    """

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Instantiate a single settings object for import throughout the project
prod_settings = ProdSettings()
