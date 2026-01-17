"""
Configuration Manager Module

Manages edge client configuration including:
- Audio settings
- Backend connections (multi-backend support)
- Logging settings
- Storage cleanup settings
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """Audio recording configuration"""
    default_device_index: int = 0
    channels: int = 1
    sample_rate: int = 16000
    bit_depth: int = 16

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AudioConfig:
        return cls(
            default_device_index=data.get('default_device_index', 0),
            channels=data.get('channels', 1),
            sample_rate=data.get('sample_rate', 16000),
            bit_depth=data.get('bit_depth', 16)
        )


@dataclass
class LoggingConfig:
    """Logging configuration"""
    enabled: bool = True
    log_dir: str = "logs"
    log_file: str = "edge_client.log"
    level: str = "DEBUG"
    max_bytes: int = 10485760  # 10 MB per file
    backup_count: int = 100
    compress_backup: bool = True
    max_total_size_gb: float = 20.0  # For legacy logger_manager compatibility
    cleanup_threshold_percent: float = 90.0
    console_output: bool = True
    console_level: str = "INFO"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> LoggingConfig:
        return cls(
            enabled=data.get('enabled', True),
            log_dir=data.get('log_dir', 'logs'),
            log_file=data.get('log_file', 'edge_client.log'),
            level=data.get('level', 'DEBUG'),
            max_bytes=data.get('max_bytes', 10485760),
            backup_count=data.get('backup_count', 100),
            compress_backup=data.get('compress_backup', True),
            max_total_size_gb=data.get('max_total_size_gb', 20.0),
            cleanup_threshold_percent=data.get('cleanup_threshold_percent', 90.0),
            console_output=data.get('console_output', True),
            console_level=data.get('console_level', 'INFO')
        )


@dataclass
class StorageCleanupConfig:
    """Storage cleanup configuration"""
    enabled: bool = True
    check_interval_hours: float = 1.0
    temp_wav_max_gb: float = 20.0
    logs_max_gb: float = 20.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> StorageCleanupConfig:
        return cls(
            enabled=data.get('enabled', True),
            check_interval_hours=data.get('check_interval_hours', 1.0),
            temp_wav_max_gb=data.get('temp_wav_max_gb', 20.0),
            logs_max_gb=data.get('logs_max_gb', 20.0)
        )


@dataclass
class BackendConfig:
    """Single backend server configuration"""
    id: str
    url: str
    is_primary: bool = False
    enabled: bool = True
    retry_count: int = 3
    retry_delay: int = 5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> BackendConfig:
        return cls(
            id=data.get('id', str(uuid.uuid4())[:8]),
            url=data.get('url', ''),
            is_primary=data.get('is_primary', False),
            enabled=data.get('enabled', True),
            retry_count=data.get('retry_count', 3),
            retry_delay=data.get('retry_delay', 5)
        )


@dataclass
class MultiBackendConfig:
    """Multi-backend behavior configuration"""
    command_dedup_seconds: int = 5
    broadcast_mode: str = "all"  # all, primary_only
    upload_strategy: str = "all"  # all, primary_first
    connection_timeout: int = 10

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MultiBackendConfig:
        return cls(
            command_dedup_seconds=data.get('command_dedup_seconds', 5),
            broadcast_mode=data.get('broadcast_mode', 'all'),
            upload_strategy=data.get('upload_strategy', 'all'),
            connection_timeout=data.get('connection_timeout', 10)
        )


@dataclass
class EdgeClientConfig:
    """Edge client main configuration"""
    device_id: str | None = None
    device_name: str = ""
    backends: list[BackendConfig] = field(default_factory=list)
    multi_backend: MultiBackendConfig = field(default_factory=MultiBackendConfig)
    audio_config: AudioConfig = field(default_factory=AudioConfig)
    logging_config: LoggingConfig = field(default_factory=LoggingConfig)
    storage_cleanup: StorageCleanupConfig = field(default_factory=StorageCleanupConfig)
    heartbeat_interval: int = 30
    reconnect_delay: int = 5
    max_reconnect_delay: int = 60
    temp_wav_dir: str = "temp_wav"

    def __post_init__(self):
        if not self.device_name:
            self.device_name = f"Device_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict:
        return {
            'device_id': self.device_id,
            'device_name': self.device_name,
            'backends': [b.to_dict() for b in self.backends],
            'multi_backend': self.multi_backend.to_dict(),
            'audio_config': self.audio_config.to_dict(),
            'logging_config': self.logging_config.to_dict(),
            'storage_cleanup': self.storage_cleanup.to_dict(),
            'heartbeat_interval': self.heartbeat_interval,
            'reconnect_delay': self.reconnect_delay,
            'max_reconnect_delay': self.max_reconnect_delay,
            'temp_wav_dir': self.temp_wav_dir
        }

    @classmethod
    def from_dict(cls, data: dict) -> EdgeClientConfig:
        # Parse backends list
        backends_data = data.get('backends', [])
        backends = [BackendConfig.from_dict(b) for b in backends_data]

        # Parse nested configs
        multi_backend = MultiBackendConfig.from_dict(data.get('multi_backend', {}))
        audio_config = AudioConfig.from_dict(data.get('audio_config', {}))
        logging_config = LoggingConfig.from_dict(data.get('logging_config', {}))
        storage_cleanup = StorageCleanupConfig.from_dict(data.get('storage_cleanup', {}))

        return cls(
            device_id=data.get('device_id'),
            device_name=data.get('device_name', ''),
            backends=backends,
            multi_backend=multi_backend,
            audio_config=audio_config,
            logging_config=logging_config,
            storage_cleanup=storage_cleanup,
            heartbeat_interval=data.get('heartbeat_interval', 30),
            reconnect_delay=data.get('reconnect_delay', 5),
            max_reconnect_delay=data.get('max_reconnect_delay', 60),
            temp_wav_dir=data.get('temp_wav_dir', 'temp_wav')
        )

    def get_primary_backend(self) -> BackendConfig | None:
        """Get the primary backend, or first enabled if none marked primary"""
        for backend in self.backends:
            if backend.is_primary and backend.enabled:
                return backend
        # Fallback to first enabled
        for backend in self.backends:
            if backend.enabled:
                return backend
        return None

    def get_enabled_backends(self) -> list[BackendConfig]:
        """Get all enabled backends"""
        return [b for b in self.backends if b.enabled]


class ConfigManager:
    """Configuration manager for edge client"""

    def __init__(self, config_file: str = 'device_config.json'):
        self.config_file = config_file
        self.config = EdgeClientConfig()
        logger.info(f"ConfigManager initialized: {config_file}")

    def load(self) -> EdgeClientConfig:
        """Load configuration from file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = EdgeClientConfig.from_dict(data)
                    logger.info(
                        f"Config loaded: device_id={self.config.device_id}, "
                        f"backends={len(self.config.backends)}"
                    )
            else:
                logger.warning(f"Config file not found: {self.config_file}, using defaults")
                self.config = EdgeClientConfig()

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            self.config = EdgeClientConfig()
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = EdgeClientConfig()

        return self.config

    def save(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Config saved: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def set_device_id(self, device_id: str) -> bool:
        """Set device ID and save"""
        self.config.device_id = device_id
        return self.save()

    def set_device_name(self, device_name: str) -> bool:
        """Set device name and save"""
        self.config.device_name = device_name
        return self.save()

    def update_audio_config(self, **kwargs) -> bool:
        """Update audio configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.audio_config, key):
                setattr(self.config.audio_config, key, value)
        return self.save()

    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration"""
        errors = []

        if not self.config.backends:
            errors.append("At least one backend must be configured")

        for backend in self.config.backends:
            if not backend.url:
                errors.append(f"Backend '{backend.id}' has no URL")
            elif not backend.url.startswith(('http://', 'https://')):
                errors.append(f"Backend '{backend.id}' URL must start with http:// or https://")

        if self.config.heartbeat_interval < 5:
            errors.append("Heartbeat interval must be at least 5 seconds")

        if self.config.audio_config.channels < 1:
            errors.append("Audio channels must be at least 1")

        if self.config.audio_config.sample_rate < 8000:
            errors.append("Sample rate must be at least 8000 Hz")

        return len(errors) == 0, errors
