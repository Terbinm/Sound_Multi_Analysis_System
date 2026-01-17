"""
Multi-Backend Manager Module

Manages connections to multiple backend servers with:
- Command aggregation and deduplication
- Result broadcasting to all backends
- Automatic reconnection and failover
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests
import socketio

from config_manager import BackendConfig, MultiBackendConfig

logger = logging.getLogger(__name__)


@dataclass
class CommandRecord:
    """Record of a received command for deduplication"""
    command_type: str
    command_hash: str
    source_backend_id: str
    received_at: datetime
    recording_uuid: str | None = None


class BackendConnection:
    """Manages a single backend WebSocket connection"""

    def __init__(
        self,
        config: BackendConfig,
        device_id: str,
        device_name: str,
        on_command: callable,
        on_status_change: callable
    ):
        self.config = config
        self.device_id = device_id
        self.device_name = device_name
        self._on_command = on_command
        self._on_status_change = on_status_change

        # SocketIO client
        self.sio = socketio.Client(
            logger=False,
            engineio_logger=False,
            reconnection=False
        )

        # Connection state
        self.status = 'DISCONNECTED'
        self.last_error: str | None = None
        self._register_handlers()

    def _register_handlers(self):
        """Register WebSocket event handlers"""

        @self.sio.on('connect')
        def on_connect():
            logger.info(f"[{self.config.id}] Connected to {self.config.url}")
            self.status = 'CONNECTED'
            self._on_status_change(self.config.id, 'CONNECTED')

        @self.sio.on('disconnect')
        def on_disconnect():
            logger.warning(f"[{self.config.id}] Disconnected")
            self.status = 'DISCONNECTED'
            self._on_status_change(self.config.id, 'DISCONNECTED')

        @self.sio.on('connect_error')
        def on_connect_error(data):
            logger.error(f"[{self.config.id}] Connection error: {data}")
            self.last_error = str(data)
            self.status = 'ERROR'
            self._on_status_change(self.config.id, 'ERROR')

        # Command handlers
        @self.sio.on('edge.registered')
        def on_registered(data):
            device_id = data.get('device_id')
            if device_id:
                logger.info(f"[{self.config.id}] Registered with device_id: {device_id}")

        @self.sio.on('edge.error')
        def on_error(data):
            error = data.get('error', 'Unknown')
            logger.error(f"[{self.config.id}] Server error: {error}")

        @self.sio.on('edge.record')
        def on_record(data):
            self._on_command('record', data, self.config.id)

        @self.sio.on('edge.stop')
        def on_stop(data):
            self._on_command('stop', data, self.config.id)

        @self.sio.on('edge.query_audio_devices')
        def on_query_devices(data):
            self._on_command('query_audio_devices', data, self.config.id)

        @self.sio.on('edge.update_config')
        def on_update_config(data):
            self._on_command('update_config', data, self.config.id)

    def connect(self) -> bool:
        """Connect to the backend server"""
        try:
            if self.sio.connected:
                return True

            self.status = 'CONNECTING'
            logger.info(f"[{self.config.id}] Connecting to {self.config.url}")
            self.sio.connect(self.config.url, wait_timeout=10)
            return True
        except Exception as e:
            self.last_error = str(e)
            self.status = 'ERROR'
            logger.error(f"[{self.config.id}] Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from the backend"""
        try:
            if self.sio.connected:
                self.sio.disconnect()
        except Exception as e:
            logger.debug(f"[{self.config.id}] Disconnect error: {e}")
        finally:
            self.status = 'DISCONNECTED'

    def emit(self, event: str, data: dict) -> bool:
        """Emit an event to this backend"""
        if not self.sio.connected:
            return False
        try:
            self.sio.emit(event, data)
            return True
        except Exception as e:
            logger.error(f"[{self.config.id}] Emit error: {e}")
            return False

    def upload_recording(self, filepath: str, metadata: dict) -> bool:
        """Upload a recording file via HTTP"""
        try:
            url = f"{self.config.url}/api/edge-devices/upload_recording"
            with open(filepath, 'rb') as f:
                files = {'file': f}
                response = requests.post(url, files=files, data=metadata, timeout=60)

            if response.status_code == 200:
                logger.info(f"[{self.config.id}] Upload successful")
                return True
            else:
                logger.error(f"[{self.config.id}] Upload failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[{self.config.id}] Upload error: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self.sio.connected and self.status == 'CONNECTED'


class CommandAggregator:
    """Handles command deduplication across multiple backends"""

    def __init__(self, dedup_seconds: int = 5):
        self.dedup_seconds = dedup_seconds
        self._history: list[CommandRecord] = []
        self._lock = threading.Lock()

    def should_execute(self, cmd_type: str, data: dict, source_id: str) -> tuple[bool, str | None]:
        """
        Check if command should be executed.
        Returns (should_execute, reason_if_skipped)
        """
        with self._lock:
            self._cleanup_expired()

            cmd_hash = self._compute_hash(cmd_type, data)

            # Check for duplicate
            for record in self._history:
                if record.command_hash == cmd_hash:
                    elapsed = (datetime.now(timezone.utc) - record.received_at).total_seconds()
                    if elapsed < self.dedup_seconds:
                        return False, f"Duplicate from {record.source_backend_id} ({elapsed:.1f}s ago)"

            # Record this command
            self._history.append(CommandRecord(
                command_type=cmd_type,
                command_hash=cmd_hash,
                source_backend_id=source_id,
                received_at=datetime.now(timezone.utc),
                recording_uuid=data.get('recording_uuid')
            ))

            return True, None

    def _compute_hash(self, cmd_type: str, data: dict) -> str:
        """Compute a hash for command deduplication"""
        # Use recording_uuid for record commands
        if cmd_type == 'record' and 'recording_uuid' in data:
            return f"record:{data['recording_uuid']}"

        # Hash the full content for other commands
        content = f"{cmd_type}:{json.dumps(data, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    def _cleanup_expired(self):
        """Remove expired command records"""
        cutoff = datetime.now(timezone.utc)
        self._history = [
            r for r in self._history
            if (cutoff - r.received_at).total_seconds() < self.dedup_seconds * 2
        ]


class MultiBackendManager:
    """
    Manages multiple backend connections with command aggregation and result broadcasting.

    Usage:
        manager = MultiBackendManager(backends, config, device_id, device_name)
        manager.on_record = handle_record
        manager.connect_all()
        manager.broadcast('edge.heartbeat', {...})
    """

    def __init__(
        self,
        backends: list[BackendConfig],
        config: MultiBackendConfig,
        device_id: str,
        device_name: str
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.config = config

        # Command handlers
        self.on_record: callable | None = None
        self.on_stop: callable | None = None
        self.on_query_audio_devices: callable | None = None
        self.on_update_config: callable | None = None

        # Internal state
        self._connections: dict[str, BackendConnection] = {}
        self._aggregator = CommandAggregator(config.command_dedup_seconds)
        self._running = False
        self._reconnect_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Initialize connections
        for backend in backends:
            if backend.enabled:
                conn = BackendConnection(
                    config=backend,
                    device_id=device_id,
                    device_name=device_name,
                    on_command=self._handle_command,
                    on_status_change=self._on_connection_change
                )
                self._connections[backend.id] = conn

    def _handle_command(self, cmd_type: str, data: dict, source_id: str):
        """Handle incoming command with deduplication"""
        should_exec, reason = self._aggregator.should_execute(cmd_type, data, source_id)

        if not should_exec:
            logger.debug(f"Skipping {cmd_type}: {reason}")
            return

        logger.info(f"Executing {cmd_type} from {source_id}")

        # Dispatch to handler
        if cmd_type == 'record' and self.on_record:
            self.on_record(data)
        elif cmd_type == 'stop' and self.on_stop:
            self.on_stop(data)
        elif cmd_type == 'query_audio_devices' and self.on_query_audio_devices:
            self.on_query_audio_devices(data)
        elif cmd_type == 'update_config' and self.on_update_config:
            self.on_update_config(data)

    def _on_connection_change(self, backend_id: str, status: str):
        """Handle connection status changes"""
        logger.debug(f"Backend {backend_id} status: {status}")

    def connect_all(self) -> dict[str, bool]:
        """Connect to all enabled backends"""
        self._running = True
        self._stop_event.clear()
        results = {}

        for backend_id, conn in self._connections.items():
            success = conn.connect()
            results[backend_id] = success
            if success:
                self._register_device(conn)

        # Start reconnection monitor
        self._start_reconnect_monitor()

        return results

    def _register_device(self, conn: BackendConnection):
        """Register device with a backend"""
        conn.emit('edge.register', {
            'device_id': self.device_id,
            'device_name': self.device_name,
            'platform': sys.platform
        })

    def _start_reconnect_monitor(self):
        """Start background reconnection thread"""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return

        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            daemon=True,
            name="BackendReconnect"
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self):
        """Monitor and reconnect disconnected backends"""
        while not self._stop_event.is_set():
            if self._stop_event.wait(10):  # Check every 10 seconds
                break

            for backend_id, conn in self._connections.items():
                if not conn.is_connected and conn.config.enabled:
                    logger.info(f"Attempting to reconnect {backend_id}")
                    if conn.connect():
                        self._register_device(conn)

    def disconnect_all(self):
        """Disconnect from all backends"""
        self._running = False
        self._stop_event.set()

        for conn in self._connections.values():
            conn.disconnect()

    def broadcast(self, event: str, data: dict) -> dict[str, bool]:
        """Broadcast an event to all connected backends"""
        results = {}
        for backend_id, conn in self._connections.items():
            if conn.is_connected:
                if self.config.broadcast_mode == 'primary_only' and not conn.config.is_primary:
                    continue
                results[backend_id] = conn.emit(event, data)
            else:
                results[backend_id] = False
        return results

    def upload_to_all(self, filepath: str, metadata: dict) -> dict[str, bool]:
        """Upload file to all backends based on upload strategy"""
        results = {}

        if self.config.upload_strategy == 'primary_first':
            # Upload to primary first
            primary = self.get_primary_connection()
            if primary and primary.is_connected:
                success = primary.upload_recording(filepath, metadata)
                results[primary.config.id] = success
                if not success:
                    return results  # Don't continue if primary fails

            # Then upload to others
            for backend_id, conn in self._connections.items():
                if backend_id not in results and conn.is_connected:
                    results[backend_id] = conn.upload_recording(filepath, metadata)
        else:
            # Upload to all
            for backend_id, conn in self._connections.items():
                if conn.is_connected:
                    results[backend_id] = conn.upload_recording(filepath, metadata)

        return results

    def get_primary_connection(self) -> BackendConnection | None:
        """Get the primary backend connection"""
        for conn in self._connections.values():
            if conn.config.is_primary and conn.is_connected:
                return conn
        # Fallback to first connected
        for conn in self._connections.values():
            if conn.is_connected:
                return conn
        return None

    def get_connected_backends(self) -> list[str]:
        """Get list of connected backend IDs"""
        return [bid for bid, conn in self._connections.items() if conn.is_connected]

    def has_any_connection(self) -> bool:
        """Check if at least one backend is connected"""
        return any(conn.is_connected for conn in self._connections.values())

    def get_status(self) -> dict:
        """Get status of all backends"""
        return {
            'total': len(self._connections),
            'connected': len(self.get_connected_backends()),
            'backends': {
                bid: {
                    'url': conn.config.url,
                    'status': conn.status,
                    'is_primary': conn.config.is_primary,
                    'last_error': conn.last_error
                }
                for bid, conn in self._connections.items()
            }
        }

    @property
    def is_running(self) -> bool:
        return self._running
