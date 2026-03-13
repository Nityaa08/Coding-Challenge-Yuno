from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    database_url: str = "sqlite+aiosqlite:///./meridian.db"
    embedder_model: str = "all-MiniLM-L6-v2"
    max_passages_per_query: int = 5
    top_k_passages: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
