"""
Tests for WebSocketManager Service

Tests cover:
- Event pushing
- Room management
- Connection tracking
- Broadcast functionality
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestWebSocketEventPushing:
    """Test WebSocket event pushing functionality"""

    @pytest.mark.unit
    def test_emit_device_status_event(self, mock_socketio_server):
        """Test emitting device status update"""
        event_data = {
            'device_id': 'device-001',
            'status': 'online',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        mock_socketio_server.emit('device.status', event_data, room='devices')

        events = mock_socketio_server.get_emitted_events('device.status')
        assert len(events) == 1
        assert events[0].data['device_id'] == 'device-001'
        assert events[0].data['status'] == 'online'

    @pytest.mark.unit
    def test_emit_recording_update_event(self, mock_socketio_server):
        """Test emitting recording update"""
        event_data = {
            'recording_uuid': 'uuid-001',
            'status': 'completed',
            'file_size': 320000,
        }

        mock_socketio_server.emit('recording.update', event_data)

        events = mock_socketio_server.get_emitted_events('recording.update')
        assert len(events) == 1
        assert events[0].data['recording_uuid'] == 'uuid-001'

    @pytest.mark.unit
    def test_emit_analysis_progress_event(self, mock_socketio_server):
        """Test emitting analysis progress update"""
        event_data = {
            'task_id': 'task-001',
            'progress': 50,
            'step': 'processing',
        }

        mock_socketio_server.emit('analysis.progress', event_data)

        events = mock_socketio_server.get_emitted_events('analysis.progress')
        assert len(events) == 1
        assert events[0].data['progress'] == 50

    @pytest.mark.unit
    def test_emit_analysis_completed_event(self, mock_socketio_server):
        """Test emitting analysis completion"""
        event_data = {
            'task_id': 'task-001',
            'recording_id': 'rec-001',
            'results': {
                'classification': 'normal',
                'confidence': 0.95,
            },
        }

        mock_socketio_server.emit('analysis.completed', event_data)

        events = mock_socketio_server.get_emitted_events('analysis.completed')
        assert len(events) == 1
        assert events[0].data['results']['classification'] == 'normal'


class TestRoomManagement:
    """Test WebSocket room management"""

    @pytest.mark.unit
    def test_client_join_room(self, mock_socketio_server):
        """Test client joining a room"""
        sid = 'client-sid-001'
        room = 'devices'

        mock_socketio_server.enter_room(sid, room)

        rooms = mock_socketio_server.rooms(sid)
        assert room in rooms

    @pytest.mark.unit
    def test_client_leave_room(self, mock_socketio_server):
        """Test client leaving a room"""
        sid = 'client-sid-001'
        room = 'devices'

        mock_socketio_server.enter_room(sid, room)
        mock_socketio_server.leave_room(sid, room)

        rooms = mock_socketio_server.rooms(sid)
        assert room not in rooms

    @pytest.mark.unit
    def test_emit_to_room(self, mock_socketio_server):
        """Test emitting event to specific room"""
        mock_socketio_server.emit('test.event', {'data': 'test'}, room='admin-room')

        events = mock_socketio_server.get_emitted_events('test.event')
        assert len(events) == 1
        assert events[0].room == 'admin-room'

    @pytest.mark.unit
    def test_client_in_multiple_rooms(self, mock_socketio_server):
        """Test client being in multiple rooms"""
        sid = 'client-sid-001'

        mock_socketio_server.enter_room(sid, 'devices')
        mock_socketio_server.enter_room(sid, 'admin')
        mock_socketio_server.enter_room(sid, 'notifications')

        rooms = mock_socketio_server.rooms(sid)
        assert 'devices' in rooms
        assert 'admin' in rooms
        assert 'notifications' in rooms


class TestConnectionTracking:
    """Test WebSocket connection tracking"""

    @pytest.mark.unit
    def test_register_device_connection(self, mock_websocket_manager):
        """Test registering device connection"""
        mock_websocket_manager.register_connection('sid-001', device_id='device-001')

        device_connections = mock_websocket_manager.get_device_connections()
        assert 'device-001' in device_connections

    @pytest.mark.unit
    def test_register_user_connection(self, mock_websocket_manager):
        """Test registering user connection"""
        mock_websocket_manager.register_connection('sid-002', user_id='user-001')

        count = mock_websocket_manager.get_connection_count()
        assert count >= 1

    @pytest.mark.unit
    def test_unregister_connection(self, mock_websocket_manager):
        """Test unregistering connection"""
        mock_websocket_manager.register_connection('sid-001', device_id='device-001')
        mock_websocket_manager.unregister_connection('sid-001')

        device_connections = mock_websocket_manager.get_device_connections()
        assert 'device-001' not in device_connections

    @pytest.mark.unit
    def test_connection_count(self, mock_websocket_manager):
        """Test getting total connection count"""
        mock_websocket_manager.register_connection('sid-001', device_id='device-001')
        mock_websocket_manager.register_connection('sid-002', device_id='device-002')
        mock_websocket_manager.register_connection('sid-003', user_id='user-001')

        count = mock_websocket_manager.get_connection_count()
        assert count == 3


class TestBroadcastFunctionality:
    """Test broadcast functionality"""

    @pytest.mark.unit
    def test_broadcast_to_all(self, mock_websocket_manager, connected_websocket_manager):
        """Test broadcasting to all connections"""
        event_data = {'message': 'System notification'}

        count = connected_websocket_manager.broadcast('notification', event_data)
        assert count > 0

    @pytest.mark.unit
    def test_push_to_specific_device(self, connected_websocket_manager):
        """Test pushing event to specific device"""
        event_data = {'command': 'start_recording'}

        count = connected_websocket_manager.push_event(
            'device.command',
            event_data,
            target_device='device-001'
        )
        assert count == 1

    @pytest.mark.unit
    def test_push_to_specific_user(self, connected_websocket_manager):
        """Test pushing event to specific user"""
        event_data = {'alert': 'New analysis result'}

        count = connected_websocket_manager.push_event(
            'user.notification',
            event_data,
            target_user='user-001'
        )
        assert count == 1

    @pytest.mark.unit
    def test_get_pushed_events(self, connected_websocket_manager):
        """Test retrieving pushed events"""
        connected_websocket_manager.push_event('test.event', {'data': 'test1'})
        connected_websocket_manager.push_event('test.event', {'data': 'test2'})
        connected_websocket_manager.push_event('other.event', {'data': 'other'})

        test_events = connected_websocket_manager.get_pushed_events('test.event')
        assert len(test_events) >= 2


class TestEventHandlers:
    """Test WebSocket event handler registration"""

    @pytest.mark.unit
    def test_register_event_handler(self, mock_socketio_server):
        """Test registering an event handler"""
        @mock_socketio_server.on('test.event')
        def handle_test(data):
            return True

        # Handler should be registered
        assert 'test.event' in str(mock_socketio_server._handlers) or \
               '/:test.event' in mock_socketio_server._handlers

    @pytest.mark.unit
    def test_trigger_event_handler(self, mock_socketio_server):
        """Test triggering an event handler"""
        result_holder = {'called': False, 'data': None}

        @mock_socketio_server.on('test.event')
        def handle_test(data):
            result_holder['called'] = True
            result_holder['data'] = data
            return True

        mock_socketio_server.trigger_handler('test.event', {'key': 'value'})

        assert result_holder['called'] is True
        assert result_holder['data']['key'] == 'value'

    @pytest.mark.unit
    def test_clear_events(self, mock_socketio_server):
        """Test clearing emitted events"""
        mock_socketio_server.emit('test1', {})
        mock_socketio_server.emit('test2', {})

        assert len(mock_socketio_server.get_emitted_events()) >= 2

        mock_socketio_server.clear_events()

        assert len(mock_socketio_server.get_emitted_events()) == 0
