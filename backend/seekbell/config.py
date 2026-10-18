from ipaddress import ip_network
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEEKBELL_", extra="ignore")

    data_dir: Path = Path("data")
    static_dir: Path = Path("frontend/dist")
    build_revision: str = Field(default="development", min_length=1, max_length=80)

    trusted_proxies: list[str] = Field(default_factory=list)

    @field_validator("trusted_proxies")
    @classmethod
    def explicit_proxy_addresses(cls, values: list[str]) -> list[str]:
        for value in values:
            network = ip_network(value)
            if network.prefixlen == 0:
                raise ValueError("Trust specific proxy addresses or subnets only")
        return values

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "seekbell.sqlite3"
