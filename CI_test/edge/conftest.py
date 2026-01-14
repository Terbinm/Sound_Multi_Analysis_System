"""
Pytest configuration and shared fixtures for edge client tests
"""
import os
import sys
import json
import tempfile
import shutil
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'sub_system', 'edge_client'))

from CI_test.edge.mocks.mock_server import MockSocketIOServer, MockSocketIOClient
from CI_test.edge.mocks.mock_audio import MockSoundDevice, MockAudioManager


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for tests"""
    dir_path = tempfile.mkdtemp(prefix='edge_test_')
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


@pytest.fixture
def sample_config() -> dict:
    """Sample device configuration"""
    return {
        "device_id": "test-device-001",
        "device_name": "Test_Device",
        "server_url": "http://localhost:55103",
        "audio_config": {
            "default_device_index": 0,
            "channels": 1,
            "sample_rate": 16000,
            "bit_depth": 16
        },
        "heartbeat_interval": 30,
        "reconnect_delay": 5,
        "max_reconnect_delay": 60,
        "temp_wav_dir": "temp_wav"
    }


@pytest.fixture
def config_file(temp_dir: str, sample_config: dict) -> str:
    """Create a temporary config file"""
    config_path = os.path.join(temp_dir, 'device_config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(sample_config, f)
    return config_path


@pytest.fixture
def mock_socketio_server() -> Generator[MockSocketIOServer, None, None]:
    """Create a mock SocketIO server"""
    server = MockSocketIOServer(auto_respond=True)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def mock_socketio_client() -> MockSocketIOClient:
    """Create a mock SocketIO client"""
    return MockSocketIOClient()


@pytest.fixture
def mock_sounddevice() -> MockSoundDevice:
    """Create a mock sounddevice module"""
    return MockSoundDevice()


@pytest.fixture
def mock_audio_manager(temp_dir: str) -> Generator[MockAudioManager, None, None]:
    """Create a mock audio manager"""
    manager = MockAudioManager(temp_dir=os.path.join(temp_dir, 'temp_wav'))
    yield manager
    manager.cleanup()


@pytest.fixture
def patched_socketio():
    """Patch socketio.Client with mock"""
    mock_client = MockSocketIOClient()

    with patch('socketio.Client', return_value=mock_client):
        yield mock_client


@pytest.fixture
def patched_sounddevice(mock_sounddevice: MockSoundDevice):
    """Patch sounddevice module with mock"""
    with patch.dict('sys.modules', {'sounddevice': mock_sounddevice}):
        yield mock_sounddevice


@pytest.fixture
def sample_heartbeat_data() -> dict:
    """Sample heartbeat data"""
    return {
        'device_id': 'test-device-001',
        'status': 'idle',
        'current_recording': None,
        'timestamp': '2026-01-14T12:00:00'
    }


@pytest.fixture
def sample_registration_data() -> dict:
    """Sample registration data"""
    return {
        'device_id': 'test-device-001',
        'device_name': 'Test_Device',
        'platform': 'win32',
        'audio_config': {
            'default_device_index': 0,
            'channels': 1,
            'sample_rate': 16000,
            'bit_depth': 16,
            'available_devices': [
                {'index': 0, 'name': 'Mock Microphone', 'max_input_channels': 2}
            ]
        }
    }


@pytest.fixture
def sample_record_command() -> dict:
    """Sample record command data"""
    return {
        'recording_uuid': 'rec-uuid-001',
        'duration': 10,
        'channels': 1,
        'sample_rate': 16000,
        'device_index': 0,
        'bit_depth': 16
    }


@pytest.fixture
def sample_recording_completed_data() -> dict:
    """Sample recording completed data"""
    return {
        'device_id': 'test-device-001',
        'recording_uuid': 'rec-uuid-001',
        'filename': 'test_recording.wav',
        'file_size': 320000,
        'file_hash': 'abc123def456',
        'actual_duration': 10
    }


# Markers
def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
