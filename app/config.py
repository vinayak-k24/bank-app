from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    use_mock_ai: bool = True
    gemini_api_key: str = ""
    use_vertex: bool = False
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gemini_fast_model: str = "gemini-2.5-flash"
    gemini_pro_model: str = "gemini-2.5-pro"

    # FraudShield (teammate's BigQuery pipeline). Auth via ADC, never a key in the repo.
    use_mock_bq: bool = True
    bq_project_id: str = ""
    bq_dataset: str = "fraudshield"
    bq_location: str = "US"

    # Comma-separated frontend origins for CORS; optional shared demo API key.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    api_key: str = ""

    @property
    def live_ai(self) -> bool:
        if self.use_mock_ai:
            return False
        return bool(self.gemini_api_key) or (self.use_vertex and bool(self.gcp_project_id))

    @property
    def live_bq(self) -> bool:
        return not self.use_mock_bq and bool(self.bq_project_id or self.gcp_project_id)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
