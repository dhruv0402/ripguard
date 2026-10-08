from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "RipGuard API"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ripguard"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    upload_dir: str = "storage/uploads"
    output_dir: str = "storage/outputs"
    max_upload_size_mb: int = 500  # video files are larger than the receipt-image case

    # Where the trained model checkpoint lives (not committed to git — see ml/README.md)
    model_checkpoint_path: str = "ml/checkpoints/ripguard_unet_best.pt"

    # Frame sampling rate for inference — process every Nth frame rather than
    # every single frame, to keep turnaround time reasonable on CPU/modest GPU
    inference_frame_sample_rate: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
