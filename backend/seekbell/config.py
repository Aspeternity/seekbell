from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEEKBELL_", extra="ignore")

    data_dir: Path = Path("data")
    static_dir: Path = Path("frontend/dist")
    build_revision: str = Field(default="development", min_length=1, max_length=80)

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "seekbell.sqlite3"
