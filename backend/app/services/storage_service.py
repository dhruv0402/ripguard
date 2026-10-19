"""
Storage Service Abstraction:
Provides a unified interface for persisting uploads and annotated outputs across
Local Disk, S3, MinIO, or Cloudflare R2 object storage.
"""

import os
import shutil
from abc import ABC, abstractmethod
from typing import BinaryIO
from app.core.config import get_settings

settings = get_settings()


class BaseStorageService(ABC):
    @abstractmethod
    async def save_file(self, file_obj: BinaryIO, relative_path: str) -> str:
        """Saves a binary file stream to storage and returns its target URI/path."""
        pass

    @abstractmethod
    def get_file_path(self, relative_path: str) -> str:
        """Returns the local path or resolved URI for the file."""
        pass

    @abstractmethod
    def file_exists(self, relative_path: str) -> bool:
        """Checks if the file exists in storage."""
        pass

    @abstractmethod
    def delete_file(self, relative_path: str) -> bool:
        """Deletes the file from storage if present."""
        pass


class LocalStorageService(BaseStorageService):
    def __init__(self, base_dir: str | None = None):
        self.base_dir = os.path.abspath(base_dir or "storage")
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "outputs"), exist_ok=True)

    async def save_file(self, file_obj: BinaryIO, relative_path: str) -> str:
        full_path = self.get_file_path(relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as dest:
            shutil.copyfileobj(file_obj, dest)
        return full_path

    def get_file_path(self, relative_path: str) -> str:
        clean_path = os.path.normpath(relative_path).lstrip(os.sep)
        return os.path.join(self.base_dir, clean_path)

    def file_exists(self, relative_path: str) -> bool:
        full_path = self.get_file_path(relative_path)
        return os.path.exists(full_path) and os.path.isfile(full_path)

    def delete_file(self, relative_path: str) -> bool:
        full_path = self.get_file_path(relative_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            return True
        return False


def get_storage_service() -> BaseStorageService:
    # Extensible factory: can instantiate S3StorageService if S3_BUCKET is configured in settings
    return LocalStorageService(base_dir="storage")


default_storage = get_storage_service()
