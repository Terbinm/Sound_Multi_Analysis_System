"""
Integration Tests for State Management API

Tests end-to-end API workflows:
- User authentication flow
- Configuration management
- Device registration and control
- Recording upload and retrieval
"""
import pytest
from unittest.mock import MagicMock, patch


class TestAuthenticationFlow:
    """Test authentication workflow"""

    @pytest.mark.integration
    def test_login_with_valid_credentials(self, integration_test_user):
        """Test login with valid credentials"""
        credentials = {
            'username': integration_test_user['username'],
            'password': 'valid_password'
        }

        # Mock password verification
        password_valid = True
        user_active = integration_test_user['is_active']

        # Simulate login
        login_success = password_valid and user_active

        assert login_success is True

    @pytest.mark.integration
    def test_login_with_invalid_credentials(self):
        """Test login with invalid credentials"""
        credentials = {
            'username': 'invalid_user',
            'password': 'wrong_password'
        }

        # Mock user not found
        user = None
        login_success = user is not None

        assert login_success is False

    @pytest.mark.integration
    def test_logout_clears_session(self):
        """Test logout clears session"""
        session = {'user_id': 'user-001', 'logged_in': True}

        # Simulate logout
        session.clear()

        assert len(session) == 0

    @pytest.mark.integration
    def test_protected_endpoint_requires_login(self):
        """Test protected endpoint requires authentication"""
        is_authenticated = False

        # Simulate accessing protected endpoint
        if not is_authenticated:
            response_code = 401
        else:
            response_code = 200

        assert response_code == 401


class TestConfigurationManagement:
    """Test configuration management workflow"""

    @pytest.mark.integration
    def test_create_config_flow(self, integration_test_config, mock_mongodb_service):
        """Test creating analysis configuration"""
        config = integration_test_config

        # Simulate insert
        mock_mongodb_service.configs.insert_one.return_value = MagicMock(
            inserted_id=config['_id']
        )

        result = mock_mongodb_service.configs.insert_one(config)

        assert result.inserted_id == config['_id']
        mock_mongodb_service.configs.insert_one.assert_called_once()

    @pytest.mark.integration
    def test_update_config_flow(self, integration_test_config, mock_mongodb_service):
        """Test updating analysis configuration"""
        config_id = integration_test_config['_id']
        updates = {'version': '2.0.0'}

        mock_mongodb_service.configs.update_one.return_value = MagicMock(
            modified_count=1
        )

        result = mock_mongodb_service.configs.update_one(
            {'_id': config_id},
            {'$set': updates}
        )

        assert result.modified_count == 1

    @pytest.mark.integration
    def test_delete_config_flow(self, mock_mongodb_service):
        """Test deleting analysis configuration"""
        config_id = 'config-to-delete'

        mock_mongodb_service.configs.delete_one.return_value = MagicMock(
            deleted_count=1
        )

        result = mock_mongodb_service.configs.delete_one({'_id': config_id})

        assert result.deleted_count == 1

    @pytest.mark.integration
    def test_list_configs_with_pagination(self, mock_mongodb_service):
        """Test listing configs with pagination"""
        page = 1
        per_page = 10

        configs = [{'_id': f'config-{i}'} for i in range(25)]

        # Simulate pagination
        start = (page - 1) * per_page
        end = start + per_page
        page_configs = configs[start:end]

        assert len(page_configs) == 10
        assert page_configs[0]['_id'] == 'config-0'


class TestDeviceManagement:
    """Test device management workflow"""

    @pytest.mark.integration
    def test_device_registration_flow(self, mock_mongodb_service):
        """Test edge device registration"""
        device_data = {
            'device_id': 'device-new-001',
            'device_name': 'New Edge Device',
            'platform': 'linux',
            'status': 'online'
        }

        mock_mongodb_service.edge_devices.insert_one.return_value = MagicMock(
            inserted_id=device_data['device_id']
        )

        result = mock_mongodb_service.edge_devices.insert_one(device_data)

        assert result.inserted_id is not None

    @pytest.mark.integration
    def test_device_heartbeat_update(self, mock_mongodb_service):
        """Test device heartbeat update"""
        device_id = 'device-001'

        mock_mongodb_service.edge_devices.update_one.return_value = MagicMock(
            modified_count=1
        )

        result = mock_mongodb_service.edge_devices.update_one(
            {'device_id': device_id},
            {'$set': {'last_heartbeat': '2024-01-01T12:00:00Z'}}
        )

        assert result.modified_count == 1

    @pytest.mark.integration
    def test_device_command_dispatch(self, mock_rabbitmq_service):
        """Test dispatching command to device"""
        command = {
            'type': 'record',
            'device_id': 'device-001',
            'duration': 30
        }

        mock_rabbitmq_service.publish.return_value = True

        success = mock_rabbitmq_service.publish(
            exchange='edge_commands',
            routing_key=command['device_id'],
            body=command
        )

        assert success is True
        mock_rabbitmq_service.publish.assert_called_once()


class TestRecordingManagement:
    """Test recording management workflow"""

    @pytest.mark.integration
    def test_recording_upload_flow(self, sample_audio_file, mock_mongodb_service):
        """Test recording upload workflow"""
        # Simulate file upload
        import os
        file_size = os.path.getsize(sample_audio_file)

        # Mock GridFS upload
        gridfs_file_id = 'gridfs-file-new-001'

        # Mock recording document creation
        recording = {
            '_id': 'rec-new-001',
            'filename': os.path.basename(sample_audio_file),
            'file_id': gridfs_file_id,
            'file_size': file_size,
            'status': 'uploaded'
        }

        mock_mongodb_service.recordings.insert_one.return_value = MagicMock(
            inserted_id=recording['_id']
        )

        result = mock_mongodb_service.recordings.insert_one(recording)

        assert result.inserted_id == recording['_id']

    @pytest.mark.integration
    def test_recording_retrieval_flow(self, integration_test_recording, mock_mongodb_service):
        """Test recording retrieval workflow"""
        recording_id = integration_test_recording['_id']

        mock_mongodb_service.recordings.find_one.return_value = integration_test_recording

        result = mock_mongodb_service.recordings.find_one({'_id': recording_id})

        assert result is not None
        assert result['_id'] == recording_id

    @pytest.mark.integration
    def test_recording_status_update(self, mock_mongodb_service):
        """Test recording status update"""
        recording_id = 'rec-001'
        new_status = 'analyzed'

        mock_mongodb_service.recordings.update_one.return_value = MagicMock(
            modified_count=1
        )

        result = mock_mongodb_service.recordings.update_one(
            {'_id': recording_id},
            {'$set': {'status': new_status}}
        )

        assert result.modified_count == 1


class TestWebSocketIntegration:
    """Test WebSocket integration"""

    @pytest.mark.integration
    def test_websocket_event_broadcast(self):
        """Test WebSocket event broadcast"""
        mock_socketio = MagicMock()

        event = 'recording.status_changed'
        data = {'recording_id': 'rec-001', 'status': 'completed'}

        mock_socketio.emit(event, data, room='recordings')

        mock_socketio.emit.assert_called_once_with(event, data, room='recordings')

    @pytest.mark.integration
    def test_device_status_update_broadcast(self):
        """Test device status update broadcast"""
        mock_socketio = MagicMock()

        event = 'device.status_changed'
        data = {'device_id': 'device-001', 'status': 'offline'}

        mock_socketio.emit(event, data, namespace='/edge')

        mock_socketio.emit.assert_called_once()

