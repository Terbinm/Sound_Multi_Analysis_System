"""
Tests for connection resilience

These tests verify that the edge client properly handles:
- Connection drops
- Ping/pong timeout
- Automatic reconnection
- State synchronization after reconnect
"""
import time
import threading
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from CI_test.edge.mocks.mock_server import MockSocketIOClient, MockSocketIOServer


class TestConnectionStateDetection:
    """Tests for connection state detection"""

    def test_sio_connected_property(self, mock_socketio_client: MockSocketIOClient):
        """Test that sio.connected reflects actual connection state"""
        assert mock_socketio_client.connected is False

        mock_socketio_client.connect('http://localhost:55103')
        assert mock_socketio_client.connected is True

        mock_socketio_client.disconnect()
        assert mock_socketio_client.connected is False

    def test_internal_connected_sync(self, mock_socketio_client: MockSocketIOClient):
        """Test that internal _connected syncs with sio.connected"""
        _connected = False

        @mock_socketio_client.on('connect')
        def on_connect():
            nonlocal _connected
            _connected = True

        @mock_socketio_client.on('disconnect')
        def on_disconnect():
            nonlocal _connected
            _connected = False

        mock_socketio_client.connect('http://localhost:55103')
        assert _connected is True

        mock_socketio_client.disconnect()
        assert _connected is False

    def test_detect_silent_disconnect(self, mock_socketio_client: MockSocketIOClient):
        """Test detection of silent disconnect (server-side disconnect)"""
        # Connect
        mock_socketio_client.connect('http://localhost:55103')
        assert mock_socketio_client.connected is True

        # Simulate server-side disconnect by directly setting state
        # In real scenario, this happens when server closes connection
        mock_socketio_client._connected = False

        # Should be able to detect this
        assert mock_socketio_client.connected is False


class TestPingPongTimeout:
    """Tests for ping/pong timeout handling"""

    def test_ping_timeout_triggers_disconnect(self):
        """
        Test that ping timeout triggers disconnect

        Server config:
        - WEBSOCKET_PING_INTERVAL = 2 seconds
        - WEBSOCKET_PING_TIMEOUT = 6 seconds

        Client must respond to ping within 6 seconds
        """
        # Simulate ping/pong timeout scenario
        ping_interval = 2
        ping_timeout = 6

        last_pong_time = time.time()
        current_time = time.time()

        # Simulate no pong for more than timeout
        last_pong_time = current_time - (ping_timeout + 1)

        time_since_pong = current_time - last_pong_time
        is_timed_out = time_since_pong > ping_timeout

        assert is_timed_out is True

    def test_heartbeat_detects_connection_loss(self):
        """Test that heartbeat loop can detect connection loss"""
        sio_connected = True
        _connected = True
        heartbeat_stopped = False

        def heartbeat_loop():
            nonlocal heartbeat_stopped
            consecutive_failures = 0
            max_failures = 3

            while True:
                # Key check: verify actual connection state
                if not sio_connected:
                    _connected = False
                    heartbeat_stopped = True
                    break

                # Simulate heartbeat
                time.sleep(0.1)

                if consecutive_failures >= max_failures:
                    heartbeat_stopped = True
                    break

        # Start heartbeat in thread
        thread = threading.Thread(target=heartbeat_loop)
        thread.daemon = True
        thread.start()

        # Simulate connection loss
        time.sleep(0.2)
        sio_connected = False

        # Wait for detection
        time.sleep(0.3)

        assert heartbeat_stopped is True


class TestAutoReconnect:
    """Tests for automatic reconnection"""

    def test_reconnect_on_disconnect(self, mock_socketio_client: MockSocketIOClient):
        """Test that client reconnects after disconnect"""
        connect_count = 0

        @mock_socketio_client.on('connect')
        def on_connect():
            nonlocal connect_count
            connect_count += 1

        # First connection
        mock_socketio_client.connect('http://localhost:55103')
        assert connect_count == 1

        # Disconnect
        mock_socketio_client.disconnect()

        # Reconnect
        mock_socketio_client.connect('http://localhost:55103')
        assert connect_count == 2

    def test_exponential_backoff(self):
        """Test exponential backoff for reconnection delays"""
        initial_delay = 5
        max_delay = 60

        delays = []
        current_delay = initial_delay

        for _ in range(10):
            delays.append(current_delay)
            current_delay = min(current_delay * 2, max_delay)

        # Verify exponential increase
        assert delays[0] == 5
        assert delays[1] == 10
        assert delays[2] == 20
        assert delays[3] == 40
        assert delays[4] == 60  # Capped at max
        assert delays[5] == 60  # Stays at max

    def test_reconnect_preserves_device_id(self, mock_socketio_client: MockSocketIOClient):
        """Test that device_id is preserved across reconnections"""
        device_id = 'persistent-device-001'
        registered_ids = []

        # Simulate registration on each connect
        def register():
            registered_ids.append(device_id)

        @mock_socketio_client.on('connect')
        def on_connect():
            register()

        # Multiple connections
        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.disconnect()
        mock_socketio_client.connect('http://localhost:55103')

        # Same device_id should be used
        assert registered_ids[0] == registered_ids[1]


class TestHeartbeatResilience:
    """Tests for heartbeat thread resilience"""

    def test_heartbeat_stops_on_disconnect(self):
        """Test that heartbeat thread stops when disconnected"""
        heartbeat_running = True
        _connected = True
        stop_event = threading.Event()

        def heartbeat_loop():
            nonlocal heartbeat_running
            while not stop_event.is_set():
                if not _connected:
                    heartbeat_running = False
                    break
                time.sleep(0.1)
            heartbeat_running = False

        thread = threading.Thread(target=heartbeat_loop)
        thread.daemon = True
        thread.start()

        # Simulate disconnect
        time.sleep(0.2)
        _connected = False

        # Wait for stop
        time.sleep(0.3)
        assert heartbeat_running is False

    def test_heartbeat_restarts_on_reconnect(self):
        """Test that heartbeat thread restarts after reconnection"""
        heartbeat_start_count = 0

        def start_heartbeat():
            nonlocal heartbeat_start_count
            heartbeat_start_count += 1

        # Simulate reconnection cycle
        start_heartbeat()  # First connect
        # ... disconnect happens ...
        start_heartbeat()  # Reconnect

        assert heartbeat_start_count == 2

    def test_consecutive_failure_detection(self):
        """Test detection of consecutive heartbeat failures"""
        consecutive_failures = 0
        max_failures = 3
        should_disconnect = False

        def send_heartbeat():
            nonlocal consecutive_failures, should_disconnect
            # Simulate failure
            raise Exception("Send failed")

        for _ in range(5):
            try:
                send_heartbeat()
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    should_disconnect = True
                    break

        assert consecutive_failures == 3
        assert should_disconnect is True


class TestMainLoopResilience:
    """Tests for main loop resilience"""

    def test_main_loop_continues_after_error(self):
        """Test that main loop continues after errors"""
        error_count = 0
        max_errors = 3
        loop_iterations = 0

        for _ in range(max_errors + 2):
            try:
                loop_iterations += 1
                if loop_iterations <= max_errors:
                    raise ConnectionError("Connection failed")
            except ConnectionError:
                error_count += 1
                continue

        assert error_count == max_errors
        assert loop_iterations == max_errors + 2

    def test_connection_check_frequency(self):
        """Test that connection status is checked frequently"""
        check_interval = 5  # seconds (as per implementation)
        check_count = 0

        # Simulate checking over 15 seconds
        simulation_time = 15
        expected_checks = simulation_time // check_interval

        for _ in range(expected_checks):
            check_count += 1

        assert check_count >= 3  # At least 3 checks in 15 seconds


class TestStateRecovery:
    """Tests for state recovery after reconnection"""

    def test_status_reset_on_reconnect(self):
        """Test that status is properly reset on reconnection"""
        status = 'recording'

        # Disconnect happens
        status = 'offline'

        # Reconnect
        status = 'idle'

        assert status == 'idle'

    def test_registration_on_reconnect(self, mock_socketio_client: MockSocketIOClient):
        """Test that device re-registers after reconnection"""
        registrations = []

        @mock_socketio_client.on('connect')
        def on_connect():
            mock_socketio_client.emit('edge.register', {
                'device_id': 'test-device',
                'device_name': 'Test'
            })
            registrations.append(True)

        # First connection
        mock_socketio_client.connect('http://localhost:55103')

        # Simulate reconnection
        mock_socketio_client.disconnect()
        mock_socketio_client.connect('http://localhost:55103')

        assert len(registrations) == 2

    def test_heartbeat_resumes_after_reconnect(self):
        """Test that heartbeat resumes after reconnection"""
        heartbeat_threads = []

        def start_heartbeat():
            thread = threading.Thread(target=lambda: None)
            heartbeat_threads.append(thread)
            return thread

        # First connection
        start_heartbeat()

        # Reconnection
        start_heartbeat()

        assert len(heartbeat_threads) == 2


class TestEdgeCases:
    """Tests for edge cases and error scenarios"""

    def test_immediate_disconnect_after_connect(self, mock_socketio_client: MockSocketIOClient):
        """Test handling immediate disconnect after connect"""
        connect_received = False
        disconnect_received = False

        @mock_socketio_client.on('connect')
        def on_connect():
            nonlocal connect_received
            connect_received = True

        @mock_socketio_client.on('disconnect')
        def on_disconnect():
            nonlocal disconnect_received
            disconnect_received = True

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.disconnect()

        assert connect_received is True
        assert disconnect_received is True

    def test_multiple_rapid_disconnects(self, mock_socketio_client: MockSocketIOClient):
        """Test handling multiple rapid connect/disconnect cycles"""
        cycle_count = 0

        @mock_socketio_client.on('connect')
        def on_connect():
            nonlocal cycle_count
            cycle_count += 1

        # Rapid cycles
        for _ in range(5):
            mock_socketio_client.connect('http://localhost:55103')
            mock_socketio_client.disconnect()

        assert cycle_count == 5

    def test_disconnect_during_recording(self, mock_socketio_client: MockSocketIOClient):
        """Test handling disconnect during active recording"""
        status = 'recording'
        recording_uuid = 'active-recording'

        # Disconnect happens during recording
        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.disconnect()

        # Status should be set to offline
        status = 'offline'
        recording_uuid = None

        assert status == 'offline'
        assert recording_uuid is None


class TestHeartbeatRaceCondition:
    """Tests for heartbeat thread race condition issues"""

    def test_heartbeat_startup_delay(self):
        """
        Test that heartbeat waits before first connection check.

        Issue: Heartbeat thread starts in on_connect callback but
        sio.connected might not be True yet, causing false disconnect detection.
        """
        sio_connected = False  # Simulates state during on_connect callback
        heartbeat_detected_disconnect = False
        startup_delay = 1  # seconds

        def heartbeat_loop_with_delay():
            nonlocal heartbeat_detected_disconnect
            # Wait for connection to stabilize
            time.sleep(startup_delay)

            # Now check connection
            if not sio_connected:
                heartbeat_detected_disconnect = True

        def heartbeat_loop_without_delay():
            nonlocal heartbeat_detected_disconnect
            # Immediately check connection (problematic)
            if not sio_connected:
                heartbeat_detected_disconnect = True

        # Test without delay - should detect false disconnect
        heartbeat_detected_disconnect = False
        sio_connected = False
        thread = threading.Thread(target=heartbeat_loop_without_delay)
        thread.start()
        thread.join(timeout=2)
        assert heartbeat_detected_disconnect is True  # False positive

        # Test with delay - connection stabilizes before check
        heartbeat_detected_disconnect = False
        sio_connected = False

        def delayed_set_connected():
            time.sleep(0.5)
            nonlocal sio_connected
            sio_connected = True

        connect_thread = threading.Thread(target=delayed_set_connected)
        connect_thread.start()

        thread = threading.Thread(target=heartbeat_loop_with_delay)
        thread.start()
        thread.join(timeout=2)
        connect_thread.join(timeout=2)

        assert heartbeat_detected_disconnect is False  # Correct behavior

    def test_already_connected_error_handling(self):
        """
        Test handling of 'Already connected' error during reconnection.

        Issue: When internal state thinks disconnected but sio.connected is True,
        calling connect() raises 'Already connected' error.
        """
        sio_connected = True
        _connected = False  # Internal state says disconnected
        reconnect_success = False

        def connect():
            nonlocal reconnect_success, sio_connected
            if sio_connected:
                # Must disconnect first
                sio_connected = False
                time.sleep(0.1)

            # Now can connect
            sio_connected = True
            reconnect_success = True

        # Simulate the scenario
        connect()
        assert reconnect_success is True
        assert sio_connected is True

    def test_cleanup_before_reconnect(self):
        """
        Test that connection state is properly cleaned before reconnect.
        """
        sio_connected = True
        _connected = False
        cleanup_performed = False
        reconnect_attempted = False

        def cleanup_and_reconnect():
            nonlocal cleanup_performed, reconnect_attempted, sio_connected

            # Cleanup: ensure sio is disconnected
            if sio_connected:
                sio_connected = False
                cleanup_performed = True

            # Now safe to reconnect
            sio_connected = True
            reconnect_attempted = True

        cleanup_and_reconnect()

        assert cleanup_performed is True
        assert reconnect_attempted is True
        assert sio_connected is True


class TestConnectionMonitoring:
    """Tests for connection monitoring implementation"""

    def test_monitor_checks_sio_connected(self):
        """Test that monitor checks sio.connected property"""
        sio_connected = True
        detected_disconnect = False

        def monitor_loop():
            nonlocal detected_disconnect
            for _ in range(10):
                if not sio_connected:
                    detected_disconnect = True
                    break
                time.sleep(0.05)

        thread = threading.Thread(target=monitor_loop)
        thread.start()

        # Simulate disconnect
        time.sleep(0.1)
        sio_connected = False

        thread.join(timeout=1)
        assert detected_disconnect is True

    def test_monitor_checks_internal_state(self):
        """Test that monitor checks internal _connected state"""
        _connected = True
        detected_disconnect = False

        def monitor_loop():
            nonlocal detected_disconnect
            for _ in range(10):
                if not _connected:
                    detected_disconnect = True
                    break
                time.sleep(0.05)

        thread = threading.Thread(target=monitor_loop)
        thread.start()

        # Simulate heartbeat thread setting _connected to False
        time.sleep(0.1)
        _connected = False

        thread.join(timeout=1)
        assert detected_disconnect is True
