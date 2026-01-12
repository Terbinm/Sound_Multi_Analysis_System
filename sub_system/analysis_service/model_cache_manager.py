# model_cache_manager.py - Model Cache Manager for GridFS Models
"""
Model cache management module.
Downloads models from MongoDB GridFS and maintains local cache.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import MODEL_REQUIREMENTS, MODEL_CACHE_CONFIG
from utils.logger import logger


class ModelCacheError(Exception):
    """Model cache operation error"""
    pass


class ModelDownloadError(ModelCacheError):
    """Failed to download model from GridFS"""
    pass


class ModelNotFoundError(ModelCacheError):
    """Required model file not found in configuration"""
    pass


class ModelCacheManager:
    """
    Model cache manager.

    Downloads models from MongoDB GridFS and maintains local cache.
    Provides methods to ensure all required models are available before analysis.
    """

    def __init__(self, cache_dir: str = None, gridfs_handler=None):
        """
        Initialize model cache manager.

        Args:
            cache_dir: Local cache directory path. Defaults to MODEL_CACHE_CONFIG['cache_dir'].
            gridfs_handler: GridFS handler for downloading files.
        """
        self.cache_dir = Path(cache_dir or MODEL_CACHE_CONFIG['cache_dir'])
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.gridfs_handler = gridfs_handler
        self._cache_index: Dict[str, Dict[str, Any]] = {}
        self._index_file = self.cache_dir / 'cache_index.json'

        self._load_cache_index()
        logger.info(f"ModelCacheManager initialized, cache_dir={self.cache_dir}")

    def _load_cache_index(self):
        """Load cache index from file"""
        if self._index_file.exists():
            try:
                with open(self._index_file, 'r', encoding='utf-8') as f:
                    self._cache_index = json.load(f)
                logger.debug(f"Loaded cache index with {len(self._cache_index)} entries")
            except Exception as e:
                logger.warning(f"Failed to load cache index: {e}")
                self._cache_index = {}

    def _save_cache_index(self):
        """Save cache index to file"""
        try:
            with open(self._index_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache_index, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"Failed to save cache index: {e}")

    def get_cached_path(self, file_id: str) -> Optional[Path]:
        """
        Get cached file path if exists.

        Args:
            file_id: GridFS file ID.

        Returns:
            Path to cached file, or None if not cached.
        """
        if file_id not in self._cache_index:
            return None

        cached_info = self._cache_index[file_id]
        cached_path = Path(cached_info.get('local_path', ''))

        if cached_path.exists():
            return cached_path

        # Cache entry exists but file is missing, remove entry
        del self._cache_index[file_id]
        self._save_cache_index()
        return None

    def download_model(self, file_id: str, filename: str) -> Path:
        """
        Download model from GridFS and cache locally.

        Args:
            file_id: GridFS file ID.
            filename: Original filename.

        Returns:
            Path to downloaded file.

        Raises:
            ModelDownloadError: If download fails.
        """
        # Check cache first
        cached_path = self.get_cached_path(file_id)
        if cached_path:
            logger.debug(f"Cache hit: {filename} ({file_id})")
            return cached_path

        # Download from GridFS
        if not self.gridfs_handler:
            raise ModelDownloadError("GridFS handler not configured")

        logger.info(f"Downloading model from GridFS: {filename} ({file_id})")

        try:
            # Download file content
            file_data = self.gridfs_handler.download_file(file_id)
            if not file_data:
                raise ModelDownloadError(f"Failed to download file: {file_id}")

            # Create cache directory for this file
            file_cache_dir = self.cache_dir / file_id
            file_cache_dir.mkdir(parents=True, exist_ok=True)

            # Save to local file
            local_path = file_cache_dir / filename
            with open(local_path, 'wb') as f:
                f.write(file_data)

            # Update cache index
            self._cache_index[file_id] = {
                'local_path': str(local_path),
                'filename': filename,
                'downloaded_at': datetime.utcnow().isoformat(),
                'size': len(file_data)
            }
            self._save_cache_index()

            logger.info(f"Model cached: {local_path} ({len(file_data)} bytes)")
            return local_path

        except Exception as e:
            logger.error(f"Failed to download model {file_id}: {e}")
            raise ModelDownloadError(f"Failed to download model: {e}") from e

    def ensure_models_for_config(self, config: Dict[str, Any]) -> Dict[str, Path]:
        """
        Ensure all required models for a configuration are downloaded.

        Args:
            config: Analysis configuration dict containing model_files.

        Returns:
            Dict mapping file_key to local path.

        Raises:
            ModelNotFoundError: If required model is not configured.
            ModelDownloadError: If model download fails.
        """
        model_files = config.get('model_files', {})
        classification_method = model_files.get('classification_method', 'random')
        files = model_files.get('files', {})

        # Get requirements for this method
        requirements = MODEL_REQUIREMENTS.get(classification_method, {})
        required_files = requirements.get('required_files', [])
        optional_files = requirements.get('optional_files', [])

        local_paths = {}

        # Process required files (must exist)
        for req in required_files:
            file_key = req['key']

            if file_key not in files:
                raise ModelNotFoundError(
                    f"Required model file not configured: {file_key} ({req['description']})"
                )

            file_info = files[file_key]
            file_id = file_info.get('file_id')
            filename = file_info.get('filename', req.get('filename', f'{file_key}.bin'))

            if not file_id:
                raise ModelNotFoundError(
                    f"Required model file has no file_id: {file_key}"
                )

            # Download and cache
            local_path = self.download_model(file_id, filename)
            local_paths[file_key] = local_path
            logger.info(f"Required model ready: {file_key} -> {local_path}")

        # Process optional files (skip if not configured)
        for opt in optional_files:
            file_key = opt['key']

            if file_key not in files:
                logger.debug(f"Optional model not configured, skipping: {file_key}")
                continue

            file_info = files[file_key]
            file_id = file_info.get('file_id')
            filename = file_info.get('filename', opt.get('filename', f'{file_key}.bin'))

            if not file_id:
                logger.debug(f"Optional model has no file_id, skipping: {file_key}")
                continue

            try:
                local_path = self.download_model(file_id, filename)
                local_paths[file_key] = local_path
                logger.info(f"Optional model ready: {file_key} -> {local_path}")
            except Exception as e:
                logger.warning(f"Failed to download optional model {file_key}: {e}")

        return local_paths

    def get_model_dir_for_config(self, config: Dict[str, Any], file_key: str = 'rf_model') -> Optional[str]:
        """
        Get the directory containing a specific model file.

        Args:
            config: Analysis configuration dict.
            file_key: Model file key.

        Returns:
            Directory path containing the model, or None.
        """
        try:
            local_paths = self.ensure_models_for_config(config)
            if file_key in local_paths:
                return str(local_paths[file_key].parent)
        except Exception as e:
            logger.warning(f"Failed to get model dir for {file_key}: {e}")
        return None

    def clear_cache(self, file_id: str = None):
        """
        Clear cache, optionally for a specific file.

        Args:
            file_id: Specific file to clear, or None to clear all.
        """
        if file_id:
            if file_id in self._cache_index:
                cached_info = self._cache_index[file_id]
                local_path = Path(cached_info.get('local_path', ''))
                if local_path.exists():
                    local_path.unlink()
                # Remove parent directory if empty
                if local_path.parent.exists() and not any(local_path.parent.iterdir()):
                    local_path.parent.rmdir()
                del self._cache_index[file_id]
                self._save_cache_index()
                logger.info(f"Cleared cache for: {file_id}")
        else:
            # Clear all cache
            for fid in list(self._cache_index.keys()):
                self.clear_cache(fid)
            # Remove any orphaned directories
            for subdir in self.cache_dir.iterdir():
                if subdir.is_dir() and subdir.name != 'cache_index.json':
                    shutil.rmtree(subdir, ignore_errors=True)
            logger.info("Cleared all model cache")

    def get_cache_size(self) -> int:
        """Get total cache size in bytes"""
        total = 0
        for info in self._cache_index.values():
            total += info.get('size', 0)
        return total

    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'cache_dir': str(self.cache_dir),
            'total_files': len(self._cache_index),
            'total_size_bytes': self.get_cache_size(),
            'total_size_mb': round(self.get_cache_size() / (1024 * 1024), 2),
            'files': list(self._cache_index.keys())
        }
