"""
Root conftest.py - Shared fixtures for all test modules
"""
import os
import sys
import json
import tempfile
import shutil
from typing import Generator, Dict, Any
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'core', 'state_management'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'sub_system', 'edge_client'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'sub_system', 'analysis_service'))

# Import mocks after path setup
from CI_test.mocks.mock_mongodb import MockMongoClient, MockDatabase, MockCollection, MockGridFS
from CI_test.mocks.mock_rabbitmq import MockChannel, MockConnection

# Register fixture plugins for pytest to discover
pytest_plugins = [
    'CI_test.fixtures.websocket_fixtures',
    'CI_test.fixtures.mongodb_fixtures',
    'CI_test.fixtures.rabbitmq_fixtures',
    'CI_test.fixtures.config_fixtures',
    'CI_test.fixtures.env_fixtures',
]


# ============================================================================
# Environment Variable Fixtures
# ============================================================================

@pytest.fixture
def base_env_vars() -> Dict[str, str]:
    """Base environment variables for testing"""
    return {
        'FLASK_ENV': 'testing',
        'FLASK_DEBUG': '0',
        'SECRET_KEY': 'test-secret-key-for-ci-testing',
        'LOG_LEVEL': 'DEBUG',
    }


@pytest.fixture
def mongodb_env_vars() -> Dict[str, str]:
    """MongoDB environment variables"""
    return {
        'MONGODB_HOST': 'localhost',
        'MONGODB_PORT': '27017',
        'MONGODB_DATABASE': 'test_sound_analysis',
        'MONGODB_USERNAME': 'test_user',
        'MONGODB_PASSWORD': 'test_password',
        'MONGODB_AUTH_SOURCE': 'admin',
    }


@pytest.fixture
def rabbitmq_env_vars() -> Dict[str, str]:
    """RabbitMQ environment variables"""
    return {
        'RABBITMQ_HOST': 'localhost',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USERNAME': 'test_user',
        'RABBITMQ_PASSWORD': 'test_password',
        'RABBITMQ_VHOST': 'test_vhost',
        'RABBITMQ_QUEUE_NAME': 'test_analysis_queue',
        'RABBITMQ_EXCHANGE_NAME': 'test_analysis_exchange',
    }


@pytest.fixture
def state_management_env_vars(
    base_env_vars: Dict[str, str],
    mongodb_env_vars: Dict[str, str],
    rabbitmq_env_vars: Dict[str, str]
) -> Dict[str, str]:
    """Complete environment variables for state management module"""
    env_vars = {}
    env_vars.update(base_env_vars)
    env_vars.update(mongodb_env_vars)
    env_vars.update(rabbitmq_env_vars)
    env_vars.update({
        'WEB_HOST': '0.0.0.0',
        'WEB_PORT': '55103',
        'UPLOAD_FOLDER': 'uploads',
    })
    return env_vars


@pytest.fixture
def analysis_service_env_vars(
    mongodb_env_vars: Dict[str, str],
    rabbitmq_env_vars: Dict[str, str]
) -> Dict[str, str]:
    """Environment variables for analysis service"""
    env_vars = {}
    env_vars.update(mongodb_env_vars)
    env_vars.update(rabbitmq_env_vars)
    env_vars.update({
        'ANALYSIS_NODE_ID': 'test-node-001',
        'MODEL_CACHE_DIR': 'models',
        'CAPABILITIES': 'audio_classification,anomaly_detection',
    })
    return env_vars


@pytest.fixture
def mock_env_vars(state_management_env_vars: Dict[str, str]):
    """Context manager to mock environment variables"""
    with patch.dict(os.environ, state_management_env_vars, clear=False):
        yield state_management_env_vars


# ============================================================================
# Temporary Directory Fixtures
# ============================================================================

@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for tests"""
    dir_path = tempfile.mkdtemp(prefix='ci_test_')
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def temp_wav_dir(temp_dir: str) -> str:
    """Create a temporary WAV directory"""
    wav_dir = os.path.join(temp_dir, 'temp_wav')
    os.makedirs(wav_dir, exist_ok=True)
    return wav_dir


@pytest.fixture
def temp_log_dir(temp_dir: str) -> str:
    """Create a temporary log directory"""
    log_dir = os.path.join(temp_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


@pytest.fixture
def temp_model_dir(temp_dir: str) -> str:
    """Create a temporary model cache directory"""
    model_dir = os.path.join(temp_dir, 'models')
    os.makedirs(model_dir, exist_ok=True)
    return model_dir


@pytest.fixture
def temp_upload_dir(temp_dir: str) -> str:
    """Create a temporary upload directory"""
    upload_dir = os.path.join(temp_dir, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


# ============================================================================
# MongoDB Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_mongo_client() -> MockMongoClient:
    """Create a mock MongoDB client"""
    return MockMongoClient()


@pytest.fixture
def mock_database(mock_mongo_client: MockMongoClient) -> MockDatabase:
    """Create a mock MongoDB database"""
    return mock_mongo_client['test_database']


@pytest.fixture
def mock_collection(mock_database: MockDatabase) -> MockCollection:
    """Create a mock MongoDB collection"""
    return mock_database['test_collection']


@pytest.fixture
def mock_gridfs() -> MockGridFS:
    """Create a mock GridFS instance"""
    return MockGridFS()


@pytest.fixture
def patched_mongodb(mock_mongo_client: MockMongoClient):
    """Patch pymongo.MongoClient with mock"""
    with patch('pymongo.MongoClient', return_value=mock_mongo_client):
        yield mock_mongo_client


# ============================================================================
# RabbitMQ Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_rabbitmq_channel() -> MockChannel:
    """Create a mock RabbitMQ channel"""
    return MockChannel()


@pytest.fixture
def mock_rabbitmq_connection(mock_rabbitmq_channel: MockChannel) -> MockConnection:
    """Create a mock RabbitMQ connection"""
    return MockConnection(mock_rabbitmq_channel)


@pytest.fixture
def patched_rabbitmq(mock_rabbitmq_connection: MockConnection):
    """Patch pika.BlockingConnection with mock"""
    with patch('pika.BlockingConnection', return_value=mock_rabbitmq_connection):
        yield mock_rabbitmq_connection


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_user_data() -> Dict[str, Any]:
    """Sample user data"""
    return {
        'username': 'test_user',
        'email': 'test@example.com',
        'password_hash': 'hashed_password_123',
        'role': 'user',
        'is_active': True,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_admin_user_data() -> Dict[str, Any]:
    """Sample admin user data"""
    return {
        'username': 'admin_user',
        'email': 'admin@example.com',
        'password_hash': 'hashed_admin_password',
        'role': 'admin',
        'is_active': True,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_analysis_config() -> Dict[str, Any]:
    """Sample analysis configuration"""
    return {
        'config_id': 'config-001',
        'config_name': 'Test Audio Classification',
        'analysis_method_id': 'audio_classification',
        'description': 'Test configuration for audio classification',
        'parameters': {
            'slice_duration': 10.0,
            'overlap': 0.5,
            'sample_rate': 16000,
        },
        'model_files': {
            'classification_method': 'onnx',
            'onnx_model': {
                'file_id': 'model-file-001',
                'filename': 'classifier.onnx',
                'version': '1.0.0',
            },
        },
        'enabled': True,
        'is_system': False,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_routing_rule() -> Dict[str, Any]:
    """Sample routing rule"""
    return {
        'rule_id': 'rule-001',
        'rule_name': 'Test Routing Rule',
        'description': 'Route audio files to analysis',
        'conditions': {
            'device_id': {'$regex': 'device-.*'},
            'file_type': 'wav',
        },
        'target_config_id': 'config-001',
        'target_mongodb_instance': 'default',
        'priority': 100,
        'enabled': True,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_mongodb_instance() -> Dict[str, Any]:
    """Sample MongoDB instance configuration"""
    return {
        'instance_id': 'test-instance-001',
        'instance_name': 'Test MongoDB Instance',
        'description': 'Test instance for CI',
        'host': 'localhost',
        'port': 27017,
        'username': 'test_user',
        'password': 'test_password',
        'database': 'test_db',
        'collection': 'recordings',
        'auth_source': 'admin',
        'enabled': True,
        'is_system': False,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_edge_device() -> Dict[str, Any]:
    """Sample edge device data"""
    return {
        'device_id': 'edge-device-001',
        'device_name': 'Test Edge Device',
        'platform': 'win32',
        'status': 'online',
        'last_heartbeat': datetime.now(timezone.utc),
        'audio_config': {
            'default_device_index': 0,
            'channels': 1,
            'sample_rate': 16000,
            'bit_depth': 16,
        },
        'registered_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_recording_document() -> Dict[str, Any]:
    """Sample recording document"""
    return {
        '_id': 'rec-001',
        'recording_uuid': 'uuid-001-002-003',
        'device_id': 'edge-device-001',
        'device_name': 'Test Edge Device',
        'filename': 'recording_20260114_120000.wav',
        'original_filename': 'recording.wav',
        'file_size': 320000,
        'duration': 10.0,
        'sample_rate': 16000,
        'channels': 1,
        'bit_depth': 16,
        'upload_status': 'completed',
        'analysis_status': 'pending',
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_task_data() -> Dict[str, Any]:
    """Sample analysis task data"""
    return {
        'task_id': 'task-001',
        'recording_id': 'rec-001',
        'analyze_uuid': 'uuid-001-002-003',
        'config_id': 'config-001',
        'analysis_method_id': 'audio_classification',
        'mongodb_instance': 'default',
        'priority': 5,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def sample_node_status() -> Dict[str, Any]:
    """Sample analysis node status"""
    return {
        'node_id': 'test-node-001',
        'capabilities': ['audio_classification', 'anomaly_detection'],
        'status': 'active',
        'current_tasks': 0,
        'max_tasks': 4,
        'last_heartbeat': datetime.now(timezone.utc),
        'registered_at': datetime.now(timezone.utc),
    }


# ============================================================================
# Flask App Fixtures
# ============================================================================

@pytest.fixture
def flask_app(mock_env_vars, patched_mongodb, patched_rabbitmq):
    """Create a Flask test application"""
    # Import here to avoid circular imports
    from state_management_main import create_app

    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['LOGIN_DISABLED'] = True

    return app


@pytest.fixture
def flask_client(flask_app):
    """Create a Flask test client"""
    return flask_app.test_client()


@pytest.fixture
def flask_app_context(flask_app):
    """Create a Flask application context"""
    with flask_app.app_context():
        yield flask_app


# ============================================================================
# Utility Functions
# ============================================================================

def create_sample_wav_file(filepath: str, duration_seconds: float = 1.0, sample_rate: int = 16000) -> str:
    """Create a sample WAV file for testing"""
    import struct

    num_samples = int(duration_seconds * sample_rate)

    # WAV header
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + num_samples * 2,  # File size - 8
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1 size
        1,   # Audio format (PCM)
        1,   # Num channels
        sample_rate,
        sample_rate * 2,  # Byte rate
        2,   # Block align
        16,  # Bits per sample
        b'data',
        num_samples * 2,  # Data size
    )

    # Generate silent audio (zeros)
    audio_data = bytes(num_samples * 2)

    with open(filepath, 'wb') as f:
        f.write(header)
        f.write(audio_data)

    return filepath


@pytest.fixture
def sample_wav_file(temp_wav_dir: str) -> str:
    """Create a sample WAV file"""
    filepath = os.path.join(temp_wav_dir, 'test_audio.wav')
    return create_sample_wav_file(filepath)


# ============================================================================
# Markers Configuration
# ============================================================================

def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (may require services)"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )
    config.addinivalue_line(
        "markers", "requires_mongodb: Tests that require MongoDB connection"
    )
    config.addinivalue_line(
        "markers", "requires_rabbitmq: Tests that require RabbitMQ connection"
    )
    config.addinivalue_line(
        "markers", "windows_only: Tests that only run on Windows"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers"""
    skip_integration = pytest.mark.skip(reason="Integration tests skipped by default")
    skip_slow = pytest.mark.skip(reason="Slow tests skipped by default")
    skip_windows = pytest.mark.skip(reason="Windows-only tests skipped on non-Windows")

    for item in items:
        # Skip integration tests unless explicitly requested
        if "integration" in item.keywords and not config.getoption("-m", default=""):
            if "integration" not in (config.getoption("-m", default="") or ""):
                item.add_marker(skip_integration)

        # Skip slow tests unless explicitly requested
        if "slow" in item.keywords and not config.getoption("--runslow", default=False):
            item.add_marker(skip_slow)

        # Skip Windows-only tests on non-Windows platforms
        if "windows_only" in item.keywords and sys.platform != "win32":
            item.add_marker(skip_windows)


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="Run slow tests"
    )
    parser.addoption(
        "--runintegration",
        action="store_true",
        default=False,
        help="Run integration tests"
    )
