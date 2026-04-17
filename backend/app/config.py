from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./data/app.db"
    CORS_ORIGINS: str = "http://localhost:5173"
    SECRET_KEY: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
