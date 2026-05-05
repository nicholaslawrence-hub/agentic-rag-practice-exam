from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    pinecone_api_key: str
    pinecone_index: str = "mcb-tutor"

    openai_api_key: str
    anthropic_api_key: str

    langchain_api_key: str = ""
    langchain_tracing_v2: str = "false"
    langchain_project: str = "mcb-tutor"

    database_url: str

    nextauth_secret: str 
    daily_message_quota: int = 50

    api_url: str = "http://localhost:8000"


settings = Settings() 
