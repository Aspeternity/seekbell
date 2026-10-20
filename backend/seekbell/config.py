from ipaddress import ip_address
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEEKBELL_", extra="ignore")

    data_dir: Path = Path("data")
    static_dir: Path = Path("frontend/dist")
    build_revision: str = Field(default="development", min_length=1, max_length=80)

    # Empty by default. Exact addresses only: never trust wildcard/all-network ingress.
    trusted_proxy_ips: str = Field(default="", max_length=1024)

    @field_validator("trusted_proxy_ips")
    @classmethod
    def valid_proxy_ips(cls, value):
        if not value:
            return ""
        addresses = []
        for item in value.split(","):
            try:
                address = ip_address(item.strip())
            except ValueError:
                raise ValueError("Trusted proxies must be exact IP addresses") from None
            if address.is_unspecified or address.is_multicast or "%" in item:
                raise ValueError("Invalid trusted proxy address")
            if str(address) not in addresses:
                addresses.append(str(address))
        if not 0 < len(addresses) <= 32:
            raise ValueError("Too many trusted proxies")
        return ",".join(addresses)

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / "seekbell.sqlite3"
