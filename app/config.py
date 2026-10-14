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

    @property
    def live_ai(self) -> bool:
        if self.use_mock_ai:
            return False
        return bool(self.gemini_api_key) or (self.use_vertex and bool(self.gcp_project_id))


@lru_cache
def get_settings() -> Settings:
    return Settings()
