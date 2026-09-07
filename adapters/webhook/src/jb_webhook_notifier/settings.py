"""Environment-backed Webhook Provider configuration."""

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebhookDestinationSettings(BaseModel):
    """Adapter-owned endpoint and optional signing secret for one opaque reference."""

    url: str
    signing_secret: SecretStr | None = None


class WebhookProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JB_WEBHOOK_", extra="ignore")

    destinations: dict[str, WebhookDestinationSettings] = Field(default_factory=dict)
    http_timeout_seconds: float = Field(default=10.0, gt=0)
    allow_insecure_loopback: bool = False
