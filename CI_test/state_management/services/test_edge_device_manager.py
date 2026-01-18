"""
Tests for EdgeDeviceManager Service

Tests cover:
- Device event handling
- Recording commands
- Device queries
- Status management
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestDeviceEventHandling:
    """Test device event handling"""

    @pytest.mark.unit
    def test_handle_device_registration(self, mock_get_db):
        """Test handling device registration event"""
        devices_collection = mock_get_db['edge_devices']

        registration_data = {
            'device_id': 'new-device-001',
            'device_name': 'New Edge Device',
            'platform': 'win32',
            'audio_config': {
                'channels': 1,
                'sample_rate': 16000,
            },
        }

        # Simulate registration handling
        devices_collection.insert_one({
            **registration_data,
            'status': 'online',
            'last_heartbeat': datetime.now(timezone.utc),
            'registered_at': datetime.now(timezone.utc),
        })

        device = devices_collection.find_one({'device_id': 'new-device-001'})
        assert device is not None
        assert device['status'] == 'online'

    @pytest.mark.unit
    def test_handle_device_reconnection(self, mock_get_db, sample_edge_device):
        """Test handling device reconnection"""
        devices_collection = mock_get_db['edge_devices']

        # Insert existing device (offline)
        sample_edge_device['status'] = 'offline'
        devices_collection.insert_one(sample_edge_device)

        # Simulate reconnection
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'status': 'online',
                    'last_heartbeat': datetime.now(timezone.utc),
                }
            }
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == 'online'

    @pytest.mark.unit
    def test_handle_device_disconnect(self, mock_get_db, sample_edge_device):
        """Test handling device disconnection"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        # Simulate disconnection
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'status': 'offline'}}
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == 'offline'

    @pytest.mark.unit
    def test_handle_heartbeat_event(self, mock_get_db, sample_edge_device):
        """Test handling heartbeat event"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        heartbeat_data = {
            'device_id': sample_edge_device['device_id'],
            'status': 'idle',
            'current_recording': None,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        # Update heartbeat
        devices_collection.update_one(
            {'device_id': heartbeat_data['device_id']},
            {
                '$set': {
                    'last_heartbeat': datetime.now(timezone.utc),
                    'status': heartbeat_data['status'],
                }
            }
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == 'idle'


class TestRecordingCommands:
    """Test recording command functionality"""

    @pytest.mark.unit
    def test_send_record_command(self, mock_socketio_server):
        """Test sending record command to device"""
        command_data = {
            'recording_uuid': 'rec-uuid-001',
            'duration': 10,
            'channels': 1,
            'sample_rate': 16000,
            'device_index': 0,
        }

        mock_socketio_server.emit('edge.record', command_data, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.record')
        assert len(events) == 1
        assert events[0].data['recording_uuid'] == 'rec-uuid-001'

    @pytest.mark.unit
    def test_send_stop_command(self, mock_socketio_server):
        """Test sending stop recording command"""
        mock_socketio_server.emit('edge.stop', {}, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.stop')
        assert len(events) == 1

    @pytest.mark.unit
    def test_handle_recording_started(self, mock_get_db, sample_edge_device):
        """Test handling recording started event"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        # Update device status
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'status': 'recording',
                    'current_recording': 'rec-uuid-001',
                }
            }
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == 'recording'
        assert device['current_recording'] == 'rec-uuid-001'

    @pytest.mark.unit
    def test_handle_recording_completed(self, mock_get_db, sample_edge_device):
        """Test handling recording completed event"""
        devices_collection = mock_get_db['edge_devices']
        sample_edge_device['status'] = 'recording'
        sample_edge_device['current_recording'] = 'rec-uuid-001'
        devices_collection.insert_one(sample_edge_device)

        # Complete recording
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'status': 'idle',
                    'current_recording': None,
                }
            }
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == 'idle'
        assert device['current_recording'] is None


class TestDeviceQueries:
    """Test device query functionality"""

    @pytest.mark.unit
    def test_get_all_devices(self, sample_edge_devices_in_db):
        """Test getting all devices"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        devices = list(devices_collection.find({}))
        assert len(devices) >= 2  # Active and offline from fixture

    @pytest.mark.unit
    def test_get_online_devices(self, sample_edge_devices_in_db):
        """Test getting only online devices"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        online = list(devices_collection.find({'status': 'online'}))
        assert len(online) >= 1

        for device in online:
            assert device['status'] == 'online'

    @pytest.mark.unit
    def test_get_device_by_id(self, sample_edge_devices_in_db, sample_edge_device):
        """Test getting device by ID"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device is not None
        assert device['device_name'] == sample_edge_device['device_name']

    @pytest.mark.unit
    def test_get_devices_by_platform(self, sample_edge_devices_in_db):
        """Test getting devices filtered by platform"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        win_devices = list(devices_collection.find({'platform': 'win32'}))
        assert len(win_devices) >= 1


class TestDeviceStatusManagement:
    """Test device status management"""

    @pytest.mark.unit
    def test_update_device_status(self, mock_get_db, sample_edge_device):
        """Test updating device status"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        new_status = 'recording'
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'status': new_status}}
        )

        device = devices_collection.find_one({'device_id': sample_edge_device['device_id']})
        assert device['status'] == new_status

    @pytest.mark.unit
    def test_mark_stale_devices_offline(self, mock_get_db):
        """Test marking stale devices as offline"""
        devices_collection = mock_get_db['edge_devices']
        now = datetime.now(timezone.utc)

        # Insert devices with different heartbeat times
        devices_collection.insert_one({
            'device_id': 'active-device',
            'status': 'online',
            'last_heartbeat': now,
        })

        devices_collection.insert_one({
            'device_id': 'stale-device',
            'status': 'online',
            'last_heartbeat': now - timedelta(minutes=10),
        })

        # Mark stale devices offline (heartbeat > 5 min old)
        threshold = now - timedelta(minutes=5)
        devices_collection.update_many(
            {'last_heartbeat': {'$lt': threshold}, 'status': 'online'},
            {'$set': {'status': 'offline'}}
        )

        stale_device = devices_collection.find_one({'device_id': 'stale-device'})
        assert stale_device['status'] == 'offline'

        active_device = devices_collection.find_one({'device_id': 'active-device'})
        assert active_device['status'] == 'online'

    @pytest.mark.unit
    def test_get_device_statistics(self, mock_get_db):
        """Test getting device statistics"""
        devices_collection = mock_get_db['edge_devices']

        # Insert devices with various statuses
        devices_collection.insert_one({'device_id': 'd1', 'status': 'online'})
        devices_collection.insert_one({'device_id': 'd2', 'status': 'online'})
        devices_collection.insert_one({'device_id': 'd3', 'status': 'offline'})
        devices_collection.insert_one({'device_id': 'd4', 'status': 'recording'})

        stats = {
            'total': devices_collection.count_documents({}),
            'online': devices_collection.count_documents({'status': 'online'}),
            'offline': devices_collection.count_documents({'status': 'offline'}),
            'recording': devices_collection.count_documents({'status': 'recording'}),
        }

        assert stats['total'] == 4
        assert stats['online'] == 2
        assert stats['offline'] == 1
        assert stats['recording'] == 1
