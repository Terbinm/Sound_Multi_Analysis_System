"""
Mock SocketIO Server for testing edge client communication
"""
import threading
import time
import uuid
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field


@dataclass
class MockEvent:
    """Represents a captured event"""
    event_name: str
    data: Any
    timestamp: float = field(default_factory=time.time)


class MockSocketIOServer:
    """
    Mock SocketIO server for testing edge client

    Usage:
        server = MockSocketIOServer()
        server.start()
        # ... run client tests ...
        server.stop()
    """

    def __init__(self, auto_respond: bool = True):
        """
        Initialize mock server

        Args:
            auto_respond: If True, automatically respond to registration events
        """
        self.auto_respond = auto_respond
        self.received_events: List[MockEvent] = []
        self.event_handlers: Dict[str, Callable] = {}
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Simulated server state
        self._is_running = False
        self._should_disconnect = False
        self._ping_interval = 2
        self._ping_timeout = 6

    def register_handler(self, event: str, handler: Callable):
        """Register a custom event handler"""
        self.event_handlers[event] = handler

    def emit_to_client(self, client_id: str, event: str, data: Any):
        """
        Simulate server emitting event to client

        In real tests, this would be used to trigger client event handlers
        """
        with self._lock:
            if client_id in self.connected_clients:
                self.connected_clients[client_id]['pending_events'].append({
                    'event': event,
                    'data': data
                })

    def receive_event(self, event: str, data: Any, client_id: str = 'default'):
        """
        Simulate receiving an event from client

        Args:
            event: Event name
            data: Event data
            client_id: Client identifier
        """
        with self._lock:
            self.received_events.append(MockEvent(event_name=event, data=data))

        # Handle auto-responses
        if self.auto_respond:
            if event == 'edge.register':
                device_id = data.get('device_id') or str(uuid.uuid4())
                self.emit_to_client(client_id, 'edge.registered', {
                    'device_id': device_id,
                    'is_new': data.get('device_id') is None
                })
            elif event == 'edge.heartbeat':
                # Just acknowledge heartbeat
                pass

        # Call custom handler if registered
        if event in self.event_handlers:
            self.event_handlers[event](data, client_id)

    def get_events_by_name(self, event_name: str) -> List[MockEvent]:
        """Get all events with specific name"""
        with self._lock:
            return [e for e in self.received_events if e.event_name == event_name]

    def get_last_event(self, event_name: str) -> Optional[MockEvent]:
        """Get the last event with specific name"""
        events = self.get_events_by_name(event_name)
        return events[-1] if events else None

    def clear_events(self):
        """Clear all received events"""
        with self._lock:
            self.received_events.clear()

    def simulate_disconnect(self, client_id: str = 'default'):
        """Simulate server-side disconnect"""
        self._should_disconnect = True

    def simulate_ping_timeout(self, client_id: str = 'default'):
        """Simulate ping/pong timeout"""
        # In real scenario, this would cause the server to disconnect the client
        self.simulate_disconnect(client_id)

    def start(self):
        """Start the mock server"""
        self._is_running = True
        self._should_disconnect = False

    def stop(self):
        """Stop the mock server"""
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running


class MockSocketIOClient:
    """
    Mock SocketIO client for testing

    This is used to simulate the client-side behavior for unit tests
    """

    def __init__(self):
        self._connected = False
        self._handlers: Dict[str, Callable] = {}
        self.emitted_events: List[MockEvent] = []
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    def on(self, event: str):
        """Decorator to register event handler"""
        def decorator(handler: Callable):
            self._handlers[event] = handler
            return handler
        return decorator

    def emit(self, event: str, data: Any):
        """Emit an event"""
        with self._lock:
            self.emitted_events.append(MockEvent(event_name=event, data=data))

    def connect(self, url: str, wait_timeout: int = 10):
        """Simulate connection"""
        self._connected = True
        if 'connect' in self._handlers:
            self._handlers['connect']()

    def disconnect(self):
        """Simulate disconnection"""
        self._connected = False
        if 'disconnect' in self._handlers:
            self._handlers['disconnect']()

    def wait(self):
        """Wait for events (blocking)"""
        while self._connected:
            time.sleep(0.1)

    def trigger_event(self, event: str, data: Any = None):
        """Trigger an event handler (for testing)"""
        if event in self._handlers:
            if data is not None:
                self._handlers[event](data)
            else:
                self._handlers[event]()

    def get_emitted_events(self, event_name: str) -> List[MockEvent]:
        """Get all emitted events with specific name"""
        with self._lock:
            return [e for e in self.emitted_events if e.event_name == event_name]

    def clear_events(self):
        """Clear all emitted events"""
        with self._lock:
            self.emitted_events.clear()
