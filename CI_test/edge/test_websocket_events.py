"""
Tests for WebSocket event handling
"""
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from CI_test.edge.mocks.mock_server import MockSocketIOClient


class TestWebSocketConnection:
    """Tests for WebSocket connection handling"""

    def test_connect_success(self, mock_socketio_client: MockSocketIOClient):
        """Test successful connection"""
        connect_called = False

        @mock_socketio_client.on('connect')
        def on_connect():
            nonlocal connect_called
            connect_called = True

        mock_socketio_client.connect('http://localhost:55103')

        assert mock_socketio_client.connected is True
        assert connect_called is True

    def test_disconnect_event(self, mock_socketio_client: MockSocketIOClient):
        """Test disconnect event handling"""
        disconnect_called = False

        @mock_socketio_client.on('disconnect')
        def on_disconnect():
            nonlocal disconnect_called
            disconnect_called = True

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.disconnect()

        assert mock_socketio_client.connected is False
        assert disconnect_called is True

    def test_emit_event(self, mock_socketio_client: MockSocketIOClient):
        """Test emitting events"""
        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.emit('edge.heartbeat', {'status': 'idle'})

        events = mock_socketio_client.get_emitted_events('edge.heartbeat')
        assert len(events) == 1
        assert events[0].data['status'] == 'idle'


class TestRegistrationEvents:
    """Tests for device registration events"""

    def test_register_event_format(self, sample_registration_data: dict):
        """Test registration event data format"""
        assert 'device_id' in sample_registration_data
        assert 'device_name' in sample_registration_data
        assert 'platform' in sample_registration_data
        assert 'audio_config' in sample_registration_data

    def test_register_with_new_device(self, mock_socketio_client: MockSocketIOClient):
        """Test registration with new device (no device_id)"""
        mock_socketio_client.connect('http://localhost:55103')

        registration_data = {
            'device_id': None,
            'device_name': 'New_Device',
            'platform': 'win32',
            'audio_config': {}
        }

        mock_socketio_client.emit('edge.register', registration_data)

        events = mock_socketio_client.get_emitted_events('edge.register')
        assert len(events) == 1
        assert events[0].data['device_id'] is None

    def test_register_with_existing_device(self, mock_socketio_client: MockSocketIOClient):
        """Test registration with existing device (has device_id)"""
        mock_socketio_client.connect('http://localhost:55103')

        registration_data = {
            'device_id': 'existing-device-001',
            'device_name': 'Existing_Device',
            'platform': 'win32',
            'audio_config': {}
        }

        mock_socketio_client.emit('edge.register', registration_data)

        events = mock_socketio_client.get_emitted_events('edge.register')
        assert len(events) == 1
        assert events[0].data['device_id'] == 'existing-device-001'

    def test_registered_response_handling(self, mock_socketio_client: MockSocketIOClient):
        """Test handling edge.registered response"""
        received_data = None

        @mock_socketio_client.on('edge.registered')
        def on_registered(data):
            nonlocal received_data
            received_data = data

        mock_socketio_client.connect('http://localhost:55103')

        # Simulate server response
        mock_socketio_client.trigger_event('edge.registered', {
            'device_id': 'assigned-device-001',
            'is_new': True
        })

        assert received_data is not None
        assert received_data['device_id'] == 'assigned-device-001'
        assert received_data['is_new'] is True


class TestHeartbeatEvents:
    """Tests for heartbeat events"""

    def test_heartbeat_event_format(self, sample_heartbeat_data: dict):
        """Test heartbeat event data format"""
        assert 'device_id' in sample_heartbeat_data
        assert 'status' in sample_heartbeat_data
        assert 'timestamp' in sample_heartbeat_data

    def test_heartbeat_emit(self, mock_socketio_client: MockSocketIOClient,
                           sample_heartbeat_data: dict):
        """Test emitting heartbeat event"""
        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.emit('edge.heartbeat', sample_heartbeat_data)

        events = mock_socketio_client.get_emitted_events('edge.heartbeat')
        assert len(events) == 1

    def test_heartbeat_with_recording_status(self, mock_socketio_client: MockSocketIOClient):
        """Test heartbeat with recording status"""
        mock_socketio_client.connect('http://localhost:55103')

        heartbeat_data = {
            'device_id': 'test-device',
            'status': 'recording',
            'current_recording': 'rec-uuid-001',
            'timestamp': '2026-01-14T12:00:00'
        }

        mock_socketio_client.emit('edge.heartbeat', heartbeat_data)

        events = mock_socketio_client.get_emitted_events('edge.heartbeat')
        assert events[0].data['status'] == 'recording'
        assert events[0].data['current_recording'] == 'rec-uuid-001'


class TestRecordingEvents:
    """Tests for recording command events"""

    def test_record_command_handling(self, mock_socketio_client: MockSocketIOClient,
                                     sample_record_command: dict):
        """Test handling record command from server"""
        received_command = None

        @mock_socketio_client.on('edge.record')
        def on_record(data):
            nonlocal received_command
            received_command = data

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.trigger_event('edge.record', sample_record_command)

        assert received_command is not None
        assert received_command['recording_uuid'] == 'rec-uuid-001'
        assert received_command['duration'] == 10

    def test_recording_started_emit(self, mock_socketio_client: MockSocketIOClient):
        """Test emitting recording started event"""
        mock_socketio_client.connect('http://localhost:55103')

        mock_socketio_client.emit('edge.recording_started', {
            'device_id': 'test-device',
            'recording_uuid': 'rec-uuid-001'
        })

        events = mock_socketio_client.get_emitted_events('edge.recording_started')
        assert len(events) == 1

    def test_recording_progress_emit(self, mock_socketio_client: MockSocketIOClient):
        """Test emitting recording progress event"""
        mock_socketio_client.connect('http://localhost:55103')

        for progress in [25, 50, 75, 100]:
            mock_socketio_client.emit('edge.recording_progress', {
                'device_id': 'test-device',
                'recording_uuid': 'rec-uuid-001',
                'progress_percent': progress
            })

        events = mock_socketio_client.get_emitted_events('edge.recording_progress')
        assert len(events) == 4
        assert events[-1].data['progress_percent'] == 100

    def test_recording_completed_emit(self, mock_socketio_client: MockSocketIOClient,
                                      sample_recording_completed_data: dict):
        """Test emitting recording completed event"""
        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.emit('edge.recording_completed', sample_recording_completed_data)

        events = mock_socketio_client.get_emitted_events('edge.recording_completed')
        assert len(events) == 1
        assert 'file_hash' in events[0].data

    def test_recording_failed_emit(self, mock_socketio_client: MockSocketIOClient):
        """Test emitting recording failed event"""
        mock_socketio_client.connect('http://localhost:55103')

        mock_socketio_client.emit('edge.recording_failed', {
            'device_id': 'test-device',
            'recording_uuid': 'rec-uuid-001',
            'error': 'Audio device not available'
        })

        events = mock_socketio_client.get_emitted_events('edge.recording_failed')
        assert len(events) == 1
        assert 'error' in events[0].data


class TestConfigUpdateEvents:
    """Tests for configuration update events"""

    def test_config_update_handling(self, mock_socketio_client: MockSocketIOClient):
        """Test handling config update from server"""
        received_config = None

        @mock_socketio_client.on('edge.update_config')
        def on_update_config(data):
            nonlocal received_config
            received_config = data

        mock_socketio_client.connect('http://localhost:55103')

        config_update = {
            'device_name': 'Updated_Device',
            'audio_config': {
                'channels': 2,
                'sample_rate': 44100
            }
        }

        mock_socketio_client.trigger_event('edge.update_config', config_update)

        assert received_config is not None
        assert received_config['device_name'] == 'Updated_Device'


class TestAudioDeviceQueryEvents:
    """Tests for audio device query events"""

    def test_query_audio_devices_handling(self, mock_socketio_client: MockSocketIOClient):
        """Test handling audio device query from server"""
        received_request = None

        @mock_socketio_client.on('edge.query_audio_devices')
        def on_query(data):
            nonlocal received_request
            received_request = data

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.trigger_event('edge.query_audio_devices', {
            'request_id': 'req-001'
        })

        assert received_request is not None
        assert received_request['request_id'] == 'req-001'

    def test_audio_devices_response_emit(self, mock_socketio_client: MockSocketIOClient):
        """Test emitting audio devices response"""
        mock_socketio_client.connect('http://localhost:55103')

        mock_socketio_client.emit('edge.audio_devices_response', {
            'device_id': 'test-device',
            'request_id': 'req-001',
            'devices': [
                {'index': 0, 'name': 'Microphone 1'},
                {'index': 1, 'name': 'Microphone 2'}
            ]
        })

        events = mock_socketio_client.get_emitted_events('edge.audio_devices_response')
        assert len(events) == 1
        assert len(events[0].data['devices']) == 2


class TestErrorEvents:
    """Tests for error event handling"""

    def test_error_event_handling(self, mock_socketio_client: MockSocketIOClient):
        """Test handling error event from server"""
        received_error = None

        @mock_socketio_client.on('edge.error')
        def on_error(data):
            nonlocal received_error
            received_error = data

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.trigger_event('edge.error', {
            'error': 'invalid_device',
            'message': 'Device not found'
        })

        assert received_error is not None
        assert received_error['error'] == 'invalid_device'
