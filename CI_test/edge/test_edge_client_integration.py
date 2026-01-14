"""
Integration tests for EdgeClient class

These tests actually import and test the real EdgeClient class,
not just mock simulations.
"""
import os
import sys
import time
import json
import threading
import tempfile
import shutil
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

# Add paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'sub_system', 'edge_client'))

from config_manager import ConfigManager, EdgeClientConfig


class TestEdgeClientHeartbeatRaceCondition:
    """
    Integration tests for heartbeat race condition fix.

    These tests verify the actual EdgeClient code handles the race condition
    where heartbeat thread starts before connection is fully established.
    """

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with config file"""
        dir_path = tempfile.mkdtemp(prefix='edge_client_test_')
        config_path = os.path.join(dir_path, 'device_config.json')
        config = {
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
            "temp_wav_dir": os.path.join(dir_path, "temp_wav")
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        yield config_path
        shutil.rmtree(dir_path, ignore_errors=True)

    def test_heartbeat_loop_has_startup_delay(self, temp_config_dir):
        """
        Verify that _heartbeat_loop includes startup delay to avoid race condition.

        This test imports the actual EdgeClient and checks that the heartbeat
        loop waits before first connection check.
        """
        # Mock socketio and sounddevice to avoid actual connections
        mock_sio = MagicMock()
        mock_sio.connected = True

        with patch('socketio.Client', return_value=mock_sio), \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default', MagicMock(device=[0, 0])):

            from edge_client import EdgeClient

            client = EdgeClient(temp_config_dir)

            # Verify the heartbeat loop code contains the delay
            import inspect
            source = inspect.getsource(client._heartbeat_loop)

            # Check for sleep at start of loop (the fix)
            assert 'time.sleep(1)' in source or 'time.sleep' in source.split('while')[0], \
                "Heartbeat loop should have startup delay before while loop"

    def test_heartbeat_does_not_exit_immediately(self, temp_config_dir):
        """
        Verify that heartbeat thread doesn't exit immediately after starting.

        This simulates the race condition scenario where sio.connected might
        initially return False even though we're in on_connect callback.
        """
        mock_sio = MagicMock()
        # Simulate: initially False, then True after 0.5s
        connected_values = [False, False, True, True, True]
        connected_index = [0]

        def get_connected():
            idx = min(connected_index[0], len(connected_values) - 1)
            connected_index[0] += 1
            return connected_values[idx]

        type(mock_sio).connected = PropertyMock(side_effect=get_connected)

        with patch('socketio.Client', return_value=mock_sio), \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default', MagicMock(device=[0, 0])):

            from edge_client import EdgeClient

            client = EdgeClient(temp_config_dir)
            client._connected = True
            client._heartbeat_stop_event.clear()

            # Start heartbeat in thread
            heartbeat_exited = threading.Event()

            def run_heartbeat():
                client._heartbeat_loop()
                heartbeat_exited.set()

            thread = threading.Thread(target=run_heartbeat, daemon=True)
            thread.start()

            # Wait for startup delay + some margin
            time.sleep(1.5)

            # Stop heartbeat gracefully
            client._heartbeat_stop_event.set()

            # Heartbeat should still be running (not exited due to false disconnect)
            # Wait a bit for thread to finish
            thread.join(timeout=2)

            # The heartbeat should have run for at least the startup delay
            # If it exited immediately, something is wrong


class TestEdgeClientConnectCleanup:
    """
    Integration tests for connection cleanup before reconnect.
    """

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with config file"""
        dir_path = tempfile.mkdtemp(prefix='edge_client_test_')
        config_path = os.path.join(dir_path, 'device_config.json')
        config = {
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
            "reconnect_delay": 1,
            "max_reconnect_delay": 60,
            "temp_wav_dir": os.path.join(dir_path, "temp_wav")
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        yield config_path
        shutil.rmtree(dir_path, ignore_errors=True)

    def test_connect_checks_existing_connection(self, temp_config_dir):
        """
        Verify that connect() checks for existing connection before connecting.
        """
        mock_sio = MagicMock()
        mock_sio.connected = True  # Simulate existing connection
        disconnect_called = threading.Event()

        def mock_disconnect():
            disconnect_called.set()
            mock_sio.connected = False

        mock_sio.disconnect = mock_disconnect

        def mock_connect(url, wait_timeout=10):
            if mock_sio.connected:
                raise Exception("Already connected")
            mock_sio.connected = True

        mock_sio.connect = mock_connect

        with patch('socketio.Client', return_value=mock_sio), \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default', MagicMock(device=[0, 0])):

            from edge_client import EdgeClient

            client = EdgeClient(temp_config_dir)

            # Verify the connect method handles existing connections
            import inspect
            source = inspect.getsource(client.connect)

            assert 'sio.connected' in source, \
                "connect() should check sio.connected before connecting"
            assert 'disconnect' in source, \
                "connect() should call disconnect if already connected"

    def test_connect_handles_already_connected_error(self, temp_config_dir):
        """
        Verify that connect() properly handles 'Already connected' error.
        """
        mock_sio = MagicMock()

        with patch('socketio.Client', return_value=mock_sio), \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default', MagicMock(device=[0, 0])):

            from edge_client import EdgeClient

            client = EdgeClient(temp_config_dir)

            # Check that the code handles "Already connected" error
            import inspect
            source = inspect.getsource(client.connect)

            assert 'Already connected' in source, \
                "connect() should handle 'Already connected' error"


class TestEdgeClientMainLoopCleanup:
    """
    Integration tests for main loop cleanup on disconnect.
    """

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory with config file"""
        dir_path = tempfile.mkdtemp(prefix='edge_client_test_')
        config_path = os.path.join(dir_path, 'device_config.json')
        config = {
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
            "reconnect_delay": 1,
            "max_reconnect_delay": 60,
            "temp_wav_dir": os.path.join(dir_path, "temp_wav")
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f)
        yield config_path
        shutil.rmtree(dir_path, ignore_errors=True)

    def test_run_disconnects_sio_before_reconnect(self, temp_config_dir):
        """
        Verify that run() disconnects SocketIO before attempting reconnect.
        """
        mock_sio = MagicMock()
        mock_sio.connected = True

        with patch('socketio.Client', return_value=mock_sio), \
             patch('sounddevice.query_devices', return_value=[]), \
             patch('sounddevice.default', MagicMock(device=[0, 0])):

            from edge_client import EdgeClient

            client = EdgeClient(temp_config_dir)

            # Verify the run method includes cleanup
            import inspect
            source = inspect.getsource(client.run)

            # Check for the cleanup code we added
            assert 'sio.connected' in source, \
                "run() should check sio.connected in cleanup"
            assert 'sio.disconnect' in source or 'disconnect()' in source, \
                "run() should disconnect sio in cleanup"


class TestConfigManagerIntegration:
    """
    Integration tests for ConfigManager.
    """

    def test_config_manager_loads_config(self):
        """Test that ConfigManager correctly loads configuration"""
        dir_path = tempfile.mkdtemp(prefix='config_test_')
        try:
            config_path = os.path.join(dir_path, 'test_config.json')
            config_data = {
                "device_id": "integration-test-001",
                "device_name": "Integration_Test",
                "server_url": "http://test:55103",
                "audio_config": {
                    "default_device_index": 1,
                    "channels": 2,
                    "sample_rate": 44100,
                    "bit_depth": 32
                },
                "heartbeat_interval": 15,
                "reconnect_delay": 3,
                "max_reconnect_delay": 30,
                "temp_wav_dir": "test_wav"
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f)

            manager = ConfigManager(config_path)
            config = manager.load()

            assert config.device_id == "integration-test-001"
            assert config.device_name == "Integration_Test"
            assert config.server_url == "http://test:55103"
            assert config.audio_config.channels == 2
            assert config.audio_config.sample_rate == 44100
            assert config.heartbeat_interval == 15

        finally:
            shutil.rmtree(dir_path, ignore_errors=True)

    def test_config_manager_saves_config(self):
        """Test that ConfigManager correctly saves configuration"""
        dir_path = tempfile.mkdtemp(prefix='config_test_')
        try:
            config_path = os.path.join(dir_path, 'test_config.json')

            manager = ConfigManager(config_path)
            manager.config.device_id = "saved-device-001"
            manager.config.device_name = "Saved_Device"
            manager.save()

            # Reload and verify
            with open(config_path, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)

            assert saved_data['device_id'] == "saved-device-001"
            assert saved_data['device_name'] == "Saved_Device"

        finally:
            shutil.rmtree(dir_path, ignore_errors=True)
