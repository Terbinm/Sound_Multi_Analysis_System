"""
Tests for EdgeDevice Model

Tests cover:
- Device registration
- Heartbeat updates
- Status management
- Audio configuration
- CRUD operations
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestEdgeDeviceModel:
    """Test EdgeDevice model CRUD operations"""

    @pytest.mark.unit
    def test_register_device_success(self, mock_get_db, sample_edge_device):
        """Test registering a new edge device"""
        devices_collection = mock_get_db['edge_devices']

        result = devices_collection.insert_one(sample_edge_device)
        assert result.inserted_id is not None

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device is not None
        assert device['device_name'] == sample_edge_device['device_name']

    @pytest.mark.unit
    def test_register_device_with_audio_config(self, mock_get_db):
        """Test registering device with audio configuration"""
        devices_collection = mock_get_db['edge_devices']

        device_data = {
            'device_id': 'audio-device-001',
            'device_name': 'Audio Configured Device',
            'platform': 'linux',
            'status': 'online',
            'audio_config': {
                'default_device_index': 0,
                'channels': 2,
                'sample_rate': 48000,
                'bit_depth': 24,
                'available_devices': [
                    {'index': 0, 'name': 'Built-in Microphone', 'max_input_channels': 2},
                    {'index': 1, 'name': 'USB Microphone', 'max_input_channels': 1},
                ],
            },
            'registered_at': datetime.now(timezone.utc),
        }

        devices_collection.insert_one(device_data)

        device = devices_collection.find_one({'device_id': 'audio-device-001'})
        assert device['audio_config']['sample_rate'] == 48000
        assert len(device['audio_config']['available_devices']) == 2

    @pytest.mark.unit
    def test_get_device_by_id(self, mock_get_db, sample_edge_device):
        """Test retrieving device by device_id"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device is not None
        assert device['platform'] == sample_edge_device['platform']

    @pytest.mark.unit
    def test_update_device(self, mock_get_db, sample_edge_device):
        """Test updating device fields"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        result = devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'device_name': 'Updated Device Name',
                    'updated_at': datetime.now(timezone.utc),
                }
            }
        )

        assert result.modified_count == 1

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['device_name'] == 'Updated Device Name'

    @pytest.mark.unit
    def test_delete_device(self, mock_get_db, sample_edge_device):
        """Test deleting a device"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        result = devices_collection.delete_one({
            'device_id': sample_edge_device['device_id']
        })
        assert result.deleted_count == 1

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device is None


class TestHeartbeatManagement:
    """Test device heartbeat functionality"""

    @pytest.mark.unit
    def test_update_heartbeat(self, mock_get_db, sample_edge_device):
        """Test updating device heartbeat timestamp"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        new_heartbeat = datetime.now(timezone.utc)
        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'last_heartbeat': new_heartbeat}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['last_heartbeat'] == new_heartbeat

    @pytest.mark.unit
    def test_identify_stale_devices(self, mock_get_db):
        """Test identifying devices with stale heartbeats"""
        devices_collection = mock_get_db['edge_devices']

        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        # Active device
        devices_collection.insert_one({
            'device_id': 'active-device',
            'last_heartbeat': now,
            'status': 'online',
        })

        # Stale device
        devices_collection.insert_one({
            'device_id': 'stale-device',
            'last_heartbeat': stale_time,
            'status': 'online',
        })

        # Find stale devices (heartbeat older than 2 minutes)
        threshold = now - timedelta(minutes=2)
        stale_devices = list(devices_collection.find({
            'last_heartbeat': {'$lt': threshold}
        }))

        assert len(stale_devices) == 1
        assert stale_devices[0]['device_id'] == 'stale-device'

    @pytest.mark.unit
    def test_heartbeat_with_status(self, mock_get_db, sample_edge_device):
        """Test heartbeat update with status information"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        heartbeat_data = {
            'last_heartbeat': datetime.now(timezone.utc),
            'status': 'recording',
            'current_recording': 'rec-uuid-001',
        }

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': heartbeat_data}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['status'] == 'recording'
        assert device['current_recording'] == 'rec-uuid-001'


class TestDeviceStatus:
    """Test device status management"""

    @pytest.mark.unit
    def test_set_device_online(self, mock_get_db, sample_edge_device):
        """Test setting device status to online"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'status': 'online'}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['status'] == 'online'

    @pytest.mark.unit
    def test_set_device_offline(self, mock_get_db, sample_edge_device):
        """Test setting device status to offline"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'status': 'offline'}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['status'] == 'offline'

    @pytest.mark.unit
    def test_set_device_recording(self, mock_get_db, sample_edge_device):
        """Test setting device status to recording"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {
                '$set': {
                    'status': 'recording',
                    'current_recording': 'rec-uuid-001',
                }
            }
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['status'] == 'recording'

    @pytest.mark.unit
    def test_get_devices_by_status(self, mock_get_db):
        """Test filtering devices by status"""
        devices_collection = mock_get_db['edge_devices']

        devices_collection.insert_one({
            'device_id': 'online-001',
            'status': 'online',
        })
        devices_collection.insert_one({
            'device_id': 'online-002',
            'status': 'online',
        })
        devices_collection.insert_one({
            'device_id': 'offline-001',
            'status': 'offline',
        })
        devices_collection.insert_one({
            'device_id': 'recording-001',
            'status': 'recording',
        })

        online_devices = list(devices_collection.find({'status': 'online'}))
        assert len(online_devices) == 2

        offline_devices = list(devices_collection.find({'status': 'offline'}))
        assert len(offline_devices) == 1

        recording_devices = list(devices_collection.find({'status': 'recording'}))
        assert len(recording_devices) == 1


class TestAudioConfiguration:
    """Test device audio configuration"""

    @pytest.mark.unit
    def test_update_audio_config(self, mock_get_db, sample_edge_device):
        """Test updating device audio configuration"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        new_audio_config = {
            'default_device_index': 1,
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
        assert device['audio_config']['channels'] == 2

    @pytest.mark.unit
    def test_update_available_audio_devices(self, mock_get_db, sample_edge_device):
        """Test updating list of available audio devices"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        available_devices = [
            {'index': 0, 'name': 'Default Mic', 'max_input_channels': 2},
            {'index': 1, 'name': 'USB Mic', 'max_input_channels': 1},
            {'index': 2, 'name': 'Line In', 'max_input_channels': 2},
        ]

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'audio_config.available_devices': available_devices}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert len(device['audio_config']['available_devices']) == 3

    @pytest.mark.unit
    def test_change_default_audio_device(self, mock_get_db, sample_edge_device):
        """Test changing the default audio device"""
        devices_collection = mock_get_db['edge_devices']
        devices_collection.insert_one(sample_edge_device)

        devices_collection.update_one(
            {'device_id': sample_edge_device['device_id']},
            {'$set': {'audio_config.default_device_index': 2}}
        )

        device = devices_collection.find_one({
            'device_id': sample_edge_device['device_id']
        })
        assert device['audio_config']['default_device_index'] == 2


class TestDeviceQueries:
    """Test device query operations"""

    @pytest.mark.unit
    def test_get_all_devices(self, mock_get_db, sample_edge_device):
        """Test retrieving all devices"""
        devices_collection = mock_get_db['edge_devices']

        devices_collection.insert_one(sample_edge_device)

        device2 = sample_edge_device.copy()
        device2['device_id'] = 'device-002'
        devices_collection.insert_one(device2)

        devices = list(devices_collection.find({}))
        assert len(devices) == 2

    @pytest.mark.unit
    def test_count_online_devices(self, mock_get_db):
        """Test counting online devices"""
        devices_collection = mock_get_db['edge_devices']

        devices_collection.insert_one({'device_id': 'dev-1', 'status': 'online'})
        devices_collection.insert_one({'device_id': 'dev-2', 'status': 'online'})
        devices_collection.insert_one({'device_id': 'dev-3', 'status': 'offline'})

        online_count = devices_collection.count_documents({'status': 'online'})
        assert online_count == 2

    @pytest.mark.unit
    def test_find_devices_by_platform(self, mock_get_db):
        """Test finding devices by platform"""
        devices_collection = mock_get_db['edge_devices']

        devices_collection.insert_one({'device_id': 'win-1', 'platform': 'win32'})
        devices_collection.insert_one({'device_id': 'win-2', 'platform': 'win32'})
        devices_collection.insert_one({'device_id': 'linux-1', 'platform': 'linux'})

        windows_devices = list(devices_collection.find({'platform': 'win32'}))
        assert len(windows_devices) == 2

        linux_devices = list(devices_collection.find({'platform': 'linux'}))
        assert len(linux_devices) == 1
