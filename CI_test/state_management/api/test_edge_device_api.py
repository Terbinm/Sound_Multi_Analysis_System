"""
Tests for EdgeDevice API

Tests cover:
- Device control endpoints
- Device status queries
- Recording commands
- Device configuration
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestDeviceControlAPI:
    """Test device control endpoints"""

    @pytest.mark.unit
    def test_start_recording_command(self, mock_socketio_server):
        """Test sending start recording command"""
        command_data = {
            'recording_uuid': 'rec-uuid-001',
            'duration': 30,
            'channels': 1,
            'sample_rate': 16000,
            'device_index': 0,
        }

        mock_socketio_server.emit('edge.record', command_data, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.record')
        assert len(events) == 1
        assert events[0].data['duration'] == 30

    @pytest.mark.unit
    def test_stop_recording_command(self, mock_socketio_server):
        """Test sending stop recording command"""
        mock_socketio_server.emit('edge.stop', {}, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.stop')
        assert len(events) == 1

    @pytest.mark.unit
    def test_query_audio_devices_command(self, mock_socketio_server):
        """Test querying available audio devices"""
        mock_socketio_server.emit('edge.query_audio_devices', {}, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.query_audio_devices')
        assert len(events) == 1

    @pytest.mark.unit
    def test_update_device_config_command(self, mock_socketio_server):
        """Test updating device configuration"""
        config_update = {
            'audio_config': {
                'default_device_index': 1,
                'sample_rate': 48000,
            },
        }

        mock_socketio_server.emit('edge.update_config', config_update, room='device-001')

        events = mock_socketio_server.get_emitted_events('edge.update_config')
        assert len(events) == 1


class TestDeviceStatusAPI:
    """Test device status query endpoints"""

    @pytest.mark.unit
    def test_get_device_status(self, sample_edge_devices_in_db, sample_edge_device):
        """Test getting device status"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })

        assert device is not None
        assert device['status'] == 'online'

    @pytest.mark.unit
    def test_get_all_devices_status(self, sample_edge_devices_in_db):
        """Test getting status of all devices"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        devices = list(devices_collection.find({}, {
            'device_id': 1,
            'device_name': 1,
            'status': 1,
            'last_heartbeat': 1,
        }))

        assert len(devices) >= 2

    @pytest.mark.unit
    def test_filter_devices_by_status(self, sample_edge_devices_in_db):
        """Test filtering devices by status"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        online = list(devices_collection.find({'status': 'online'}))
        offline = list(devices_collection.find({'status': 'offline'}))

        assert len(online) >= 1
        assert len(offline) >= 1

    @pytest.mark.unit
    def test_get_device_statistics(self, sample_edge_devices_in_db):
        """Test getting device statistics"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        stats = {
            'total': devices_collection.count_documents({}),
            'online': devices_collection.count_documents({'status': 'online'}),
            'offline': devices_collection.count_documents({'status': 'offline'}),
            'recording': devices_collection.count_documents({'status': 'recording'}),
        }

        assert stats['total'] >= 2
        assert stats['online'] + stats['offline'] + stats['recording'] <= stats['total']


class TestDeviceRegistration:
    """Test device registration endpoints"""

    @pytest.mark.unit
    def test_register_new_device(self, mock_get_db):
        """Test registering a new device"""
        devices_collection = mock_get_db['edge_devices']

        registration_data = {
            'device_id': 'new-device-001',
            'device_name': 'New Device',
            'platform': 'linux',
            'audio_config': {
                'default_device_index': 0,
                'channels': 1,
                'sample_rate': 16000,
            },
        }

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
    def test_update_existing_device(self, mock_get_db, sample_edge_device):
        """Test updating existing device on reconnection"""
        devices_collection = mock_get_db['edge_devices']
        sample_edge_device['status'] = 'offline'
        devices_collection.insert_one(sample_edge_device)

        # Device reconnects
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'status': 'online',
                    'last_heartbeat': datetime.now(timezone.utc),
                }
            }
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['status'] == 'online'

    @pytest.mark.unit
    def test_unregister_device(self, mock_get_db, sample_edge_device):
        """Test unregistering a device"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        result = devices_collection.delete_one({
            'device_id': sample_edge_device['device_id']
        })

        assert result.deleted_count == 1


class TestRecordingHistory:
    """Test recording history for devices"""

    @pytest.mark.unit
    def test_get_device_recordings(self, mock_get_db, sample_edge_device):
        """Test getting recordings for a device"""
        recordings_collection = mock_get_db['recordings']

        # Insert some recordings
        for i in range(5):
            recordings_collection.insert_one({
                'recording_uuid': f'rec-{i}',
                'device_id': sample_edge_device['device_id'],
                'filename': f'recording_{i}.wav',
                'created_at': datetime.now(timezone.utc),
            })

        recordings = list(recordings_collection.find({
            'device_id': sample_edge_device['device_id']
        }))

        assert len(recordings) == 5

    @pytest.mark.unit
    def test_get_recent_recordings(self, mock_get_db, sample_edge_device):
        """Test getting recent recordings"""
        recordings_collection = mock_get_db['recordings']
        now = datetime.now(timezone.utc)

        # Insert old and new recordings
        recordings_collection.insert_one({
            'recording_uuid': 'old-rec',
            'device_id': sample_edge_device['device_id'],
            'created_at': now - timedelta(days=30),
        })
        recordings_collection.insert_one({
            'recording_uuid': 'new-rec',
            'device_id': sample_edge_device['device_id'],
            'created_at': now - timedelta(hours=1),
        })

        # Get recordings from last 7 days
        threshold = now - timedelta(days=7)
        recent = list(recordings_collection.find({
            'device_id': sample_edge_device['device_id'],
            'created_at': {'$gte': threshold},
        }))

        assert len(recent) == 1
        assert recent[0]['recording_uuid'] == 'new-rec'

    @pytest.mark.unit
    def test_get_recording_count_by_device(self, mock_get_db):
        """Test counting recordings by device"""
        recordings_collection = mock_get_db['recordings']

        # Insert recordings for different devices
        for i in range(3):
            recordings_collection.insert_one({
                'recording_uuid': f'dev1-rec-{i}',
                'device_id': 'device-001',
            })
        for i in range(5):
            recordings_collection.insert_one({
                'recording_uuid': f'dev2-rec-{i}',
                'device_id': 'device-002',
            })

        count_dev1 = recordings_collection.count_documents({'device_id': 'device-001'})
        count_dev2 = recordings_collection.count_documents({'device_id': 'device-002'})

        assert count_dev1 == 3
        assert count_dev2 == 5


class TestDeviceConfiguration:
    """Test device configuration management"""

    @pytest.mark.unit
    def test_get_device_config(self, sample_edge_devices_in_db, sample_edge_device):
        """Test getting device configuration"""
        devices_collection = sample_edge_devices_in_db['edge_devices']

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })

        audio_config = device.get('audio_config', {})
        assert 'sample_rate' in audio_config

    @pytest.mark.unit
    def test_update_device_audio_config(self, mock_get_db, sample_edge_device):
        """Test updating device audio configuration"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        new_audio_config = {
            'default_device_index': 2,
            'channels': 2,
            'sample_rate': 48000,
            'bit_depth': 24,
        }

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'audio_config': new_audio_config}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['audio_config']['sample_rate'] == 48000

    @pytest.mark.unit
    def test_get_available_audio_devices(self, mock_get_db, sample_edge_device):
        """Test getting available audio devices from edge device"""
        devices_collection = mock_get_db['edge_devices']

        sample_edge_device['audio_config']['available_devices'] = [
            {'index': 0, 'name': 'Built-in Mic', 'max_input_channels': 2},
            {'index': 1, 'name': 'USB Mic', 'max_input_channels': 1},
        ]
        devices_collection.insert_one(sample_edge_device)

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })

        available = device['audio_config']['available_devices']
        assert len(available) == 2
        assert available[0]['name'] == 'Built-in Mic'
