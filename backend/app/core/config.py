from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "RipGuard API"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ripguard"
    redis_url: str | None = None

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    upload_dir: str = "storage/uploads"
    output_dir: str = "storage/outputs"
    max_upload_size_mb: int = 500  # video files are larger than the receipt-image case

    # Where the trained model checkpoint lives (v4 DeepLabV3+ with ASPP and Focal Tversky Loss)
    model_checkpoint_path: str = "ml/checkpoints/ripguard_v4_deeplab_best.pt"

    # Frame sampling rate for inference — process every Nth frame rather than
    # every single frame, to keep turnaround time reasonable on CPU/modest GPU
    inference_frame_sample_rate: int = 5

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

