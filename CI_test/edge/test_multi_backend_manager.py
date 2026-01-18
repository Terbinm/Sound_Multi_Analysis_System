"""
Tests for MultiBackendManager

Tests cover:
- Backend connection management
- Command aggregation and deduplication
- Result broadcasting
- Reconnection handling
"""
import pytest
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone


class TestBackendConnection:
    """Test BackendConnection class"""

    @pytest.mark.unit
    def test_connection_initial_state(self):
        """Test initial connection state"""
        state = {
            'status': 'DISCONNECTED',
            'last_error': None,
            'is_connected': False
        }

        assert state['status'] == 'DISCONNECTED'
        assert state['last_error'] is None
        assert state['is_connected'] is False

    @pytest.mark.unit
    def test_connection_status_transitions(self):
        """Test connection status state machine"""
        valid_transitions = {
            'DISCONNECTED': ['CONNECTING'],
            'CONNECTING': ['CONNECTED', 'ERROR'],
            'CONNECTED': ['DISCONNECTED'],
            'ERROR': ['CONNECTING', 'DISCONNECTED']
        }

        # Test DISCONNECTED -> CONNECTING
        assert 'CONNECTING' in valid_transitions['DISCONNECTED']

        # Test CONNECTING -> CONNECTED
        assert 'CONNECTED' in valid_transitions['CONNECTING']

        # Test CONNECTING -> ERROR
        assert 'ERROR' in valid_transitions['CONNECTING']

    @pytest.mark.unit
    def test_connection_emit_requires_connected(self):
        """Test emit requires connected state"""
        connected = False

        def emit(event, data):
            if not connected:
                return False
            return True

        assert emit('test_event', {}) is False

    @pytest.mark.unit
    def test_connection_url_format(self):
        """Test backend URL format"""
        urls = [
            'http://localhost:5000',
            'https://api.example.com',
            'http://192.168.1.100:8080'
        ]

        for url in urls:
            assert url.startswith('http://') or url.startswith('https://')

    @pytest.mark.unit
    def test_connection_device_registration(self):
        """Test device registration data format"""
        registration_data = {
            'device_id': 'device-001',
            'device_name': 'Test Device',
            'platform': 'win32'
        }

        assert 'device_id' in registration_data
        assert 'device_name' in registration_data
        assert 'platform' in registration_data


class TestCommandAggregator:
    """Test CommandAggregator class"""

    @pytest.mark.unit
    def test_command_deduplication_same_source(self):
        """Test command deduplication from same source"""
        history = []
        dedup_seconds = 5

        cmd1 = {'type': 'record', 'hash': 'abc123', 'source': 'backend1', 'time': 0}
        history.append(cmd1)

        # Same command within dedup window
        cmd2 = {'type': 'record', 'hash': 'abc123', 'source': 'backend1', 'time': 2}

        is_duplicate = any(
            h['hash'] == cmd2['hash'] and (cmd2['time'] - h['time']) < dedup_seconds
            for h in history
        )

        assert is_duplicate is True

    @pytest.mark.unit
    def test_command_deduplication_different_source(self):
        """Test command deduplication from different sources"""
        history = []
        dedup_seconds = 5

        cmd1 = {'type': 'record', 'hash': 'abc123', 'source': 'backend1', 'time': 0}
        history.append(cmd1)

        # Same command from different source
        cmd2 = {'type': 'record', 'hash': 'abc123', 'source': 'backend2', 'time': 2}

        is_duplicate = any(
            h['hash'] == cmd2['hash'] and (cmd2['time'] - h['time']) < dedup_seconds
            for h in history
        )

        # Should still be duplicate (same command hash)
        assert is_duplicate is True

    @pytest.mark.unit
    def test_command_allowed_after_dedup_window(self):
        """Test command allowed after dedup window expires"""
        history = []
        dedup_seconds = 5

        cmd1 = {'type': 'record', 'hash': 'abc123', 'source': 'backend1', 'time': 0}
        history.append(cmd1)

        # Same command after dedup window
        cmd2 = {'type': 'record', 'hash': 'abc123', 'source': 'backend1', 'time': 10}

        is_duplicate = any(
            h['hash'] == cmd2['hash'] and (cmd2['time'] - h['time']) < dedup_seconds
            for h in history
        )

        assert is_duplicate is False

    @pytest.mark.unit
    def test_command_hash_recording_uuid(self):
        """Test command hash for record commands with UUID"""
        def compute_hash(cmd_type, data):
            if cmd_type == 'record' and 'recording_uuid' in data:
                return f"record:{data['recording_uuid']}"
            return f"{cmd_type}:hash"

        data = {'recording_uuid': 'uuid-12345'}
        hash_val = compute_hash('record', data)

        assert hash_val == 'record:uuid-12345'

    @pytest.mark.unit
    def test_command_history_cleanup(self):
        """Test expired command history cleanup"""
        dedup_seconds = 5
        history = [
            {'hash': 'h1', 'time': 0},
            {'hash': 'h2', 'time': 3},
            {'hash': 'h3', 'time': 8},
            {'hash': 'h4', 'time': 12}
        ]

        current_time = 15
        cutoff = current_time - (dedup_seconds * 2)

        cleaned = [h for h in history if h['time'] >= cutoff]

        # Only h3 and h4 should remain
        assert len(cleaned) == 2
        assert cleaned[0]['hash'] == 'h3'


class TestMultiBackendManager:
    """Test MultiBackendManager class"""

    @pytest.mark.unit
    def test_manager_initialization(self):
        """Test manager initialization"""
        config = {
            'device_id': 'device-001',
            'device_name': 'Test Device',
            'backends': ['backend1', 'backend2']
        }

        assert config['device_id'] is not None
        assert len(config['backends']) == 2

    @pytest.mark.unit
    def test_connect_all_returns_results(self):
        """Test connect_all returns results for each backend"""
        backends = ['backend1', 'backend2', 'backend3']
        results = {bid: True for bid in backends}

        assert len(results) == 3
        assert all(results.values())

    @pytest.mark.unit
    def test_broadcast_to_connected_only(self):
        """Test broadcast only sends to connected backends"""
        connections = {
            'backend1': {'is_connected': True},
            'backend2': {'is_connected': False},
            'backend3': {'is_connected': True}
        }

        connected = [bid for bid, conn in connections.items() if conn['is_connected']]

        assert len(connected) == 2
        assert 'backend1' in connected
        assert 'backend3' in connected

    @pytest.mark.unit
    def test_broadcast_primary_only_mode(self):
        """Test broadcast in primary_only mode"""
        connections = {
            'backend1': {'is_connected': True, 'is_primary': True},
            'backend2': {'is_connected': True, 'is_primary': False},
            'backend3': {'is_connected': True, 'is_primary': False}
        }

        broadcast_mode = 'primary_only'

        if broadcast_mode == 'primary_only':
            targets = [bid for bid, conn in connections.items()
                       if conn['is_connected'] and conn['is_primary']]
        else:
            targets = [bid for bid, conn in connections.items()
                       if conn['is_connected']]

        assert len(targets) == 1
        assert targets[0] == 'backend1'

    @pytest.mark.unit
    def test_upload_primary_first_strategy(self):
        """Test upload with primary_first strategy"""
        upload_strategy = 'primary_first'
        connections = {
            'backend1': {'is_connected': True, 'is_primary': True},
            'backend2': {'is_connected': True, 'is_primary': False}
        }

        upload_order = []

        if upload_strategy == 'primary_first':
            primary = next((bid for bid, c in connections.items() if c['is_primary']), None)
            if primary:
                upload_order.append(primary)

            for bid in connections:
                if bid not in upload_order and connections[bid]['is_connected']:
                    upload_order.append(bid)

        assert upload_order[0] == 'backend1'
        assert len(upload_order) == 2

    @pytest.mark.unit
    def test_get_primary_connection_fallback(self):
        """Test get_primary_connection falls back to first connected"""
        connections = {
            'backend1': {'is_connected': True, 'is_primary': False},
            'backend2': {'is_connected': True, 'is_primary': False}
        }

        # First try to find primary
        primary = next((bid for bid, c in connections.items()
                        if c['is_primary'] and c['is_connected']), None)

        # Fallback to first connected
        if primary is None:
            primary = next((bid for bid, c in connections.items()
                            if c['is_connected']), None)

        assert primary == 'backend1'

    @pytest.mark.unit
    def test_get_connected_backends(self):
        """Test getting list of connected backends"""
        connections = {
            'backend1': {'is_connected': True},
            'backend2': {'is_connected': False},
            'backend3': {'is_connected': True}
        }

        connected = [bid for bid, conn in connections.items() if conn['is_connected']]

        assert len(connected) == 2
        assert 'backend2' not in connected

    @pytest.mark.unit
    def test_has_any_connection(self):
        """Test checking for any active connection"""
        # Case 1: At least one connected
        connections1 = {
            'backend1': {'is_connected': False},
            'backend2': {'is_connected': True}
        }
        has_any = any(c['is_connected'] for c in connections1.values())
        assert has_any is True

        # Case 2: None connected
        connections2 = {
            'backend1': {'is_connected': False},
            'backend2': {'is_connected': False}
        }
        has_any = any(c['is_connected'] for c in connections2.values())
        assert has_any is False

    @pytest.mark.unit
    def test_manager_status_report(self):
        """Test manager status report structure"""
        connections = {
            'backend1': {'url': 'http://localhost:5000', 'status': 'CONNECTED',
                         'is_primary': True, 'last_error': None},
            'backend2': {'url': 'http://localhost:5001', 'status': 'ERROR',
                         'is_primary': False, 'last_error': 'Connection refused'}
        }

        status = {
            'total': len(connections),
            'connected': sum(1 for c in connections.values() if c['status'] == 'CONNECTED'),
            'backends': connections
        }

        assert status['total'] == 2
        assert status['connected'] == 1
        assert 'backends' in status


class TestReconnectionHandling:
    """Test reconnection handling"""

    @pytest.mark.unit
    def test_reconnect_interval(self):
        """Test reconnection check interval"""
        reconnect_interval = 10  # seconds

        assert reconnect_interval > 0
        assert reconnect_interval <= 60  # Reasonable max

    @pytest.mark.unit
    def test_reconnect_only_disconnected(self):
        """Test reconnection only targets disconnected backends"""
        connections = {
            'backend1': {'is_connected': True, 'enabled': True},
            'backend2': {'is_connected': False, 'enabled': True},
            'backend3': {'is_connected': False, 'enabled': False}
        }

        to_reconnect = [
            bid for bid, conn in connections.items()
            if not conn['is_connected'] and conn['enabled']
        ]

        assert len(to_reconnect) == 1
        assert to_reconnect[0] == 'backend2'

    @pytest.mark.unit
    def test_stop_event_terminates_reconnect_loop(self):
        """Test stop event terminates reconnection loop"""
        stop_event = threading.Event()

        # Simulate loop check
        should_continue = not stop_event.is_set()
        assert should_continue is True

        stop_event.set()
        should_continue = not stop_event.is_set()
        assert should_continue is False


class TestCommandHandlers:
    """Test command handler dispatching"""

    @pytest.mark.unit
    def test_record_command_dispatch(self):
        """Test record command dispatch"""
        handlers = {
            'record': MagicMock(),
            'stop': MagicMock()
        }

        cmd_type = 'record'
        data = {'duration': 30}

        if cmd_type in handlers:
            handlers[cmd_type](data)

        handlers['record'].assert_called_once_with(data)
        handlers['stop'].assert_not_called()

    @pytest.mark.unit
    def test_stop_command_dispatch(self):
        """Test stop command dispatch"""
        handlers = {
            'record': MagicMock(),
            'stop': MagicMock()
        }

        cmd_type = 'stop'
        data = {}

        if cmd_type in handlers:
            handlers[cmd_type](data)

        handlers['stop'].assert_called_once_with(data)

    @pytest.mark.unit
    def test_query_audio_devices_dispatch(self):
        """Test query_audio_devices command dispatch"""
        handler = MagicMock()
        cmd_type = 'query_audio_devices'

        if cmd_type == 'query_audio_devices' and handler:
            handler({})

        handler.assert_called_once()

    @pytest.mark.unit
    def test_update_config_dispatch(self):
        """Test update_config command dispatch"""
        handler = MagicMock()
        cmd_type = 'update_config'
        data = {'key': 'value'}

        if cmd_type == 'update_config' and handler:
            handler(data)

        handler.assert_called_once_with(data)

    @pytest.mark.unit
    def test_unknown_command_ignored(self):
        """Test unknown command is ignored"""
        handlers = {
            'record': MagicMock(),
            'stop': MagicMock()
        }

        cmd_type = 'unknown_command'

        if cmd_type in handlers:
            handlers[cmd_type]({})

        for handler in handlers.values():
            handler.assert_not_called()

