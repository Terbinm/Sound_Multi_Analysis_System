"""
WebSocket Fixtures for Testing

Provides fixtures for:
- SocketIO server mocking
- WebSocket manager mocking
- Edge device communication testing
"""
import pytest
import threading
import time
from typing import Dict, Any, List, Generator, Callable, Optional
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class MockSocketIOEvent:
    """Represents a captured SocketIO event"""
    event_name: str
    data: Any
    room: Optional[str] = None
    namespace: str = '/'
    timestamp: float = field(default_factory=time.time)


class MockSocketIOServer:
    """
    Mock SocketIO server for testing WebSocket communication

    Usage:
        def test_websocket(mock_socketio_server):
            mock_socketio_server.emit('event', {'data': 'test'})
            events = mock_socketio_server.get_emitted_events('event')
    """

    def __init__(self):
        self._emitted_events: List[MockSocketIOEvent] = []
        self._handlers: Dict[str, Callable] = {}
        self._rooms: Dict[str, List[str]] = {}  # room_name -> [sid, ...]
        self._sids: Dict[str, Dict[str, Any]] = {}  # sid -> client info
        self._is_running = False
        self._lock = threading.Lock()

    def emit(self, event: str, data: Any = None, room: str = None,
             namespace: str = '/', skip_sid: str = None, **kwargs) -> None:
        """Emit an event to clients"""
        with self._lock:
            self._emitted_events.append(MockSocketIOEvent(
                event_name=event,
                data=data,
                room=room,
                namespace=namespace,
            ))

    def on(self, event: str, namespace: str = '/') -> Callable:
        """Decorator to register event handler"""
        def decorator(handler: Callable):
            self._handlers[f"{namespace}:{event}"] = handler
            return handler
        return decorator

    def enter_room(self, sid: str, room: str, namespace: str = '/') -> None:
        """Add client to room"""
        with self._lock:
            if room not in self._rooms:
                self._rooms[room] = []
            if sid not in self._rooms[room]:
                self._rooms[room].append(sid)

    def leave_room(self, sid: str, room: str, namespace: str = '/') -> None:
        """Remove client from room"""
        with self._lock:
            if room in self._rooms and sid in self._rooms[room]:
                self._rooms[room].remove(sid)

    def rooms(self, sid: str, namespace: str = '/') -> List[str]:
        """Get rooms for a client"""
        with self._lock:
            return [room for room, sids in self._rooms.items() if sid in sids]

    def get_emitted_events(self, event_name: str = None) -> List[MockSocketIOEvent]:
        """Get emitted events, optionally filtered by name"""
        with self._lock:
            if event_name:
                return [e for e in self._emitted_events if e.event_name == event_name]
            return self._emitted_events[:]

    def clear_events(self) -> None:
        """Clear all emitted events"""
        with self._lock:
            self._emitted_events.clear()

    def trigger_handler(self, event: str, *args, namespace: str = '/', sid: str = 'test-sid') -> Any:
        """Trigger an event handler (for testing)"""
        key = f"{namespace}:{event}"
        if key in self._handlers:
            # Call handler with just the args, not the sid
            # Flask-SocketIO handlers typically receive data, not sid
            return self._handlers[key](*args)
        return None

    def start(self) -> None:
        """Start the mock server"""
        self._is_running = True

    def stop(self) -> None:
        """Stop the mock server"""
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running


class MockWebSocketManager:
    """
    Mock WebSocket manager for state management module

    Simulates the WebSocket manager used for pushing updates to connected clients
    """

    def __init__(self):
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._pushed_events: List[MockSocketIOEvent] = []
        self._lock = threading.Lock()

    def register_connection(self, sid: str, device_id: str = None, user_id: str = None) -> None:
        """Register a new WebSocket connection"""
        with self._lock:
            self._connections[sid] = {
                'device_id': device_id,
                'user_id': user_id,
                'connected_at': datetime.now(timezone.utc),
            }

    def unregister_connection(self, sid: str) -> None:
        """Unregister a WebSocket connection"""
        with self._lock:
            self._connections.pop(sid, None)

    def push_event(self, event_type: str, data: Dict[str, Any],
                   target_device: str = None, target_user: str = None) -> int:
        """Push event to connections"""
        targets = 0
        with self._lock:
            for sid, info in self._connections.items():
                if target_device and info.get('device_id') != target_device:
                    continue
                if target_user and info.get('user_id') != target_user:
                    continue
                self._pushed_events.append(MockSocketIOEvent(
                    event_name=event_type,
                    data=data,
                    room=sid,
                ))
                targets += 1
        return targets

    def broadcast(self, event_type: str, data: Dict[str, Any]) -> int:
        """Broadcast event to all connections"""
        return self.push_event(event_type, data)

    def get_pushed_events(self, event_type: str = None) -> List[MockSocketIOEvent]:
        """Get pushed events, optionally filtered by type"""
        with self._lock:
            if event_type:
                return [e for e in self._pushed_events if e.event_name == event_type]
            return self._pushed_events[:]

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._connections)

    def get_device_connections(self) -> Dict[str, str]:
        """Get device_id -> sid mapping"""
        with self._lock:
            return {
                info['device_id']: sid
                for sid, info in self._connections.items()
                if info.get('device_id')
            }

    def clear(self) -> None:
        """Clear all connections and events"""
        with self._lock:
            self._connections.clear()
            self._pushed_events.clear()


@pytest.fixture
def mock_socketio_server() -> Generator[MockSocketIOServer, None, None]:
    """
    Create a mock SocketIO server

    Usage:
        def test_socketio(mock_socketio_server):
            mock_socketio_server.emit('update', {'status': 'active'})
    """
    server = MockSocketIOServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def mock_websocket_manager() -> Generator[MockWebSocketManager, None, None]:
    """
    Create a mock WebSocket manager

    Usage:
        def test_push_event(mock_websocket_manager):
            mock_websocket_manager.register_connection('sid1', device_id='dev1')
            mock_websocket_manager.push_event('update', {'data': 'test'})
    """
    manager = MockWebSocketManager()
    yield manager
    manager.clear()


@pytest.fixture
def connected_websocket_manager(mock_websocket_manager: MockWebSocketManager) -> MockWebSocketManager:
    """
    WebSocket manager with pre-registered connections

    Sets up sample device and user connections
    """
    # Register device connections
    mock_websocket_manager.register_connection('sid-device-001', device_id='device-001')
    mock_websocket_manager.register_connection('sid-device-002', device_id='device-002')

    # Register user connections
    mock_websocket_manager.register_connection('sid-user-001', user_id='user-001')
    mock_websocket_manager.register_connection('sid-user-002', user_id='user-002')

    return mock_websocket_manager


@pytest.fixture
def patched_socketio(mock_socketio_server: MockSocketIOServer):
    """
    Patch flask_socketio.SocketIO with mock

    Usage:
        def test_with_socketio(patched_socketio, flask_app):
            # SocketIO is mocked
            pass
    """
    with patch('flask_socketio.SocketIO', return_value=mock_socketio_server):
        yield mock_socketio_server


@pytest.fixture
def sample_websocket_events() -> List[Dict[str, Any]]:
    """
    Sample WebSocket events for testing

    Returns a list of common event types and their data
    """
    now = datetime.now(timezone.utc).isoformat()

    return [
        {
            'event': 'edge.register',
            'data': {
                'device_id': 'device-001',
                'device_name': 'Test Device',
                'platform': 'win32',
                'audio_config': {
                    'channels': 1,
                    'sample_rate': 16000,
                },
            },
        },
        {
            'event': 'edge.heartbeat',
            'data': {
                'device_id': 'device-001',
                'status': 'idle',
                'timestamp': now,
            },
        },
        {
            'event': 'edge.recording_completed',
            'data': {
                'device_id': 'device-001',
                'recording_uuid': 'uuid-001',
                'filename': 'recording.wav',
                'file_size': 320000,
            },
        },
        {
            'event': 'analysis.status',
            'data': {
                'task_id': 'task-001',
                'status': 'processing',
                'progress': 50,
            },
        },
        {
            'event': 'analysis.completed',
            'data': {
                'task_id': 'task-001',
                'recording_id': 'rec-001',
                'results': {
                    'classification': 'normal',
                    'confidence': 0.95,
                },
            },
        },
    ]
