"""
Integration Test Fixtures

Provides fixtures for integration testing including:
- Mock services (MongoDB, RabbitMQ)
- Test data
- Environment setup
"""
import pytest
import os
import tempfile
from unittest.mock import MagicMock, patch


@pytest.fixture
def integration_env_vars():
    """Environment variables for integration tests"""
    return {
        'FLASK_ENV': 'testing',
        'SECRET_KEY': 'test-secret-key-integration',
        'MONGODB_URI': 'mongodb://localhost:27017',
        'MONGODB_DB_NAME': 'test_integration_db',
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USER': 'guest',
        'RABBITMQ_PASS': 'guest',
        'UPLOAD_FOLDER': '/tmp/test_uploads'
    }


@pytest.fixture
def mock_mongodb_service():
    """Mock MongoDB service for integration tests"""
    service = MagicMock()

    # Collections
    service.users = MagicMock()
    service.configs = MagicMock()
    service.recordings = MagicMock()
    service.routing_rules = MagicMock()
    service.edge_devices = MagicMock()

    # Basic operations
    service.is_connected = True

    return service


@pytest.fixture
def mock_rabbitmq_service():
    """Mock RabbitMQ service for integration tests"""
    service = MagicMock()

    service.is_connected = True
    service.channel = MagicMock()
    service.publish = MagicMock(return_value=True)
    service.consume = MagicMock()

    return service


@pytest.fixture
def integration_test_user():
    """Test user for integration tests"""
    return {
        '_id': 'user-int-001',
        'username': 'integration_user',
        'email': 'integration@test.com',
        'password_hash': 'hashed_password',
        'role': 'admin',
        'is_active': True
    }


@pytest.fixture
def integration_test_config():
    """Test analysis config for integration tests"""
    return {
        '_id': 'config-int-001',
        'name': 'Integration Test Config',
        'version': '1.0.0',
        'pipeline_steps': [
            {'step': 0, 'name': 'converter', 'enabled': True},
            {'step': 1, 'name': 'slicer', 'enabled': True},
            {'step': 2, 'name': 'leaf', 'enabled': True},
            {'step': 3, 'name': 'classifier', 'enabled': True}
        ],
        'parameters': {
            'sample_rate': 16000,
            'slice_duration': 10.0,
            'overlap': 0.5
        },
        'model_files': {
            'leaf': 'models/leaf_v1.onnx',
            'classifier': 'models/classifier_v1.onnx'
        }
    }


@pytest.fixture
def integration_test_recording():
    """Test recording document for integration tests"""
    return {
        '_id': 'rec-int-001',
        'device_id': 'device-int-001',
        'filename': 'test_recording.wav',
        'duration': 60.0,
        'sample_rate': 16000,
        'channels': 1,
        'file_id': 'gridfs-file-int-001',
        'status': 'pending',
        'created_at': '2024-01-01T00:00:00Z'
    }


@pytest.fixture
def integration_test_routing_rule():
    """Test routing rule for integration tests"""
    return {
        '_id': 'rule-int-001',
        'name': 'Integration Test Rule',
        'priority': 100,
        'is_active': True,
        'conditions': [
            {'field': 'device_id', 'operator': 'equals', 'value': 'device-int-001'}
        ],
        'actions': {
            'config_id': 'config-int-001',
            'mongodb_instance': 'default'
        }
    }


@pytest.fixture
def temp_upload_dir():
    """Temporary upload directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_audio_file(temp_upload_dir):
    """Create a sample audio file for testing"""
    import struct

    filepath = os.path.join(temp_upload_dir, 'test_audio.wav')

    # Create minimal WAV file
    sample_rate = 16000
    num_samples = sample_rate * 5  # 5 seconds
    channels = 1
    bits_per_sample = 16

    data_size = num_samples * channels * (bits_per_sample // 8)
    file_size = 36 + data_size

    with open(filepath, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', file_size))
        f.write(b'WAVE')

        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))  # chunk size
        f.write(struct.pack('<H', 1))   # audio format (PCM)
        f.write(struct.pack('<H', channels))
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', sample_rate * channels * (bits_per_sample // 8)))
        f.write(struct.pack('<H', channels * (bits_per_sample // 8)))
        f.write(struct.pack('<H', bits_per_sample))

        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', data_size))

        # Write silence
        for _ in range(num_samples):
            f.write(struct.pack('<h', 0))

    return filepath

