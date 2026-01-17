"""
Storage Cleaner Module

Provides scheduled cleanup for directories with size limits.
Automatically removes oldest files when directory exceeds threshold.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CleanupTarget:
    """Cleanup target configuration"""
    name: str
    directory: str
    max_size_gb: float = 20.0
    threshold_percent: float = 90.0
    target_percent: float = 70.0
    file_patterns: list[str] = field(default_factory=lambda: ['*'])

    @property
    def max_bytes(self) -> int:
        return int(self.max_size_gb * 1024 * 1024 * 1024)

    @property
    def threshold_bytes(self) -> int:
        return int(self.max_bytes * self.threshold_percent / 100)

    @property
    def target_bytes(self) -> int:
        return int(self.max_bytes * self.target_percent / 100)


class StorageCleaner:
    """
    Storage cleaner with scheduled background cleanup.

    Usage:
        cleaner = StorageCleaner()
        cleaner.add_target(CleanupTarget(
            name='temp_wav',
            directory='/path/to/temp',
            max_size_gb=20.0,
            file_patterns=['*.wav']
        ))
        cleaner.start(interval_seconds=3600)  # Check every hour
    """

    def __init__(self):
        self._targets: dict[str, CleanupTarget] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False

    def add_target(self, target: CleanupTarget) -> None:
        """Add a cleanup target"""
        self._targets[target.name] = target
        self._locks[target.name] = threading.Lock()
        logger.info(f"Added cleanup target: {target.name} -> {target.directory}")

    def remove_target(self, name: str) -> bool:
        """Remove a cleanup target"""
        if name in self._targets:
            del self._targets[name]
            del self._locks[name]
            logger.info(f"Removed cleanup target: {name}")
            return True
        return False

    def start(self, interval_seconds: int = 3600) -> None:
        """Start background scheduler"""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._stop_event.clear()
        self._running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            args=(interval_seconds,),
            daemon=True,
            name="StorageCleaner"
        )
        self._scheduler_thread.start()
        logger.info(f"Storage cleaner started (interval: {interval_seconds}s)")

    def stop(self) -> None:
        """Stop background scheduler"""
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5)

        logger.info("Storage cleaner stopped")

    def _scheduler_loop(self, interval_seconds: int) -> None:
        """Scheduler main loop"""
        # Run immediately on start
        self.cleanup_all()

        while not self._stop_event.is_set():
            if self._stop_event.wait(interval_seconds):
                break
            self.cleanup_all()

    def cleanup_all(self) -> dict:
        """Check and cleanup all targets"""
        results = {}
        for name in self._targets:
            results[name] = self.cleanup(name)
        return results

    def cleanup(self, target_name: str) -> dict:
        """Check and cleanup a specific target"""
        result: dict = {
            'target': target_name,
            'checked': False,
            'cleaned': False,
            'current_mb': 0,
            'freed_mb': 0,
            'deleted_count': 0,
            'error': None
        }

        if target_name not in self._targets:
            result['error'] = f"Target '{target_name}' not found"
            return result

        target = self._targets[target_name]
        lock = self._locks[target_name]

        with lock:
            try:
                if not os.path.exists(target.directory):
                    result['checked'] = True
                    return result

                # Calculate current size
                current_size = self._calculate_size(target)
                result['current_mb'] = round(current_size / 1024 / 1024, 2)
                result['checked'] = True

                # Check if cleanup needed
                if current_size > target.threshold_bytes:
                    freed, deleted = self._do_cleanup(target, current_size)
                    result['cleaned'] = True
                    result['freed_mb'] = round(freed / 1024 / 1024, 2)
                    result['deleted_count'] = deleted

            except Exception as e:
                logger.error(f"Cleanup error for '{target_name}': {e}")
                result['error'] = str(e)

        return result

    def _calculate_size(self, target: CleanupTarget) -> int:
        """Calculate total size of matching files"""
        total = 0
        for filename in os.listdir(target.directory):
            filepath = os.path.join(target.directory, filename)
            if not os.path.isfile(filepath):
                continue
            if self._matches_patterns(filename, target.file_patterns):
                total += os.path.getsize(filepath)
        return total

    def _matches_patterns(self, filename: str, patterns: list[str]) -> bool:
        """Check if filename matches any pattern"""
        if '*' in patterns:
            return True
        return any(fnmatch.fnmatch(filename, p) for p in patterns)

    def _do_cleanup(self, target: CleanupTarget, current_size: int) -> tuple[int, int]:
        """Perform cleanup, returns (freed_bytes, deleted_count)"""
        logger.info(
            f"[{target.name}] Starting cleanup: "
            f"current={current_size / 1024 / 1024:.1f}MB, "
            f"limit={target.max_bytes / 1024 / 1024:.1f}MB"
        )

        # Collect matching files with stats
        files = []
        for filename in os.listdir(target.directory):
            filepath = os.path.join(target.directory, filename)
            if not os.path.isfile(filepath):
                continue
            if self._matches_patterns(filename, target.file_patterns):
                stat = os.stat(filepath)
                files.append({
                    'path': filepath,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                })

        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x['mtime'])

        # Delete until under target
        freed = 0
        deleted = 0

        for f in files:
            if current_size - freed <= target.target_bytes:
                break
            try:
                os.remove(f['path'])
                freed += f['size']
                deleted += 1
                logger.debug(f"Deleted: {f['path']}")
            except Exception as e:
                logger.warning(f"Failed to delete {f['path']}: {e}")

        logger.info(
            f"[{target.name}] Cleanup complete: "
            f"deleted={deleted}, freed={freed / 1024 / 1024:.1f}MB"
        )

        return freed, deleted

    def get_status(self) -> dict:
        """Get status of all targets"""
        status = {}
        for name, target in self._targets.items():
            info: dict = {
                'directory': target.directory,
                'max_gb': target.max_size_gb,
                'threshold_percent': target.threshold_percent,
                'file_patterns': target.file_patterns,
                'exists': os.path.exists(target.directory),
                'current_mb': 0,
                'usage_percent': 0.0
            }

            if info['exists']:
                size = self._calculate_size(target)
                info['current_mb'] = round(size / 1024 / 1024, 2)
                info['usage_percent'] = round(size / target.max_bytes * 100, 1)

            status[name] = info

        return status

    @property
    def is_running(self) -> bool:
        return self._running
