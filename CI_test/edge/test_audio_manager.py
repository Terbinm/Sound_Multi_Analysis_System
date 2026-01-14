"""
Tests for AudioManager module
"""
import os
import pytest
from unittest.mock import patch, MagicMock

from CI_test.edge.mocks.mock_audio import MockSoundDevice, MockAudioDevice


class TestAudioManager:
    """Tests for AudioManager class"""

    def test_list_devices(self, mock_audio_manager):
        """Test listing audio devices"""
        devices = mock_audio_manager.list_devices()

        assert len(devices) >= 1
        assert devices[0]['max_input_channels'] > 0

    def test_list_devices_as_dict(self, mock_audio_manager):
        """Test listing devices as dictionary format"""
        devices = mock_audio_manager.list_devices_as_dict()

        assert len(devices) >= 1
        assert 'index' in devices[0]
        assert 'name' in devices[0]
        assert 'max_input_channels' in devices[0]

    def test_validate_valid_config(self, mock_audio_manager):
        """Test validation with valid configuration"""
        result = mock_audio_manager.validate_recording_config(
            device_index=0,
            channels=1,
            sample_rate=16000
        )

        assert result['valid'] is True

    def test_validate_invalid_device_index(self, mock_audio_manager):
        """Test validation with invalid device index"""
        result = mock_audio_manager.validate_recording_config(
            device_index=999,
            channels=1,
            sample_rate=16000
        )

        assert result['valid'] is False
        assert 'error' in result

    def test_validate_too_many_channels(self, mock_audio_manager):
        """Test validation with too many channels"""
        result = mock_audio_manager.validate_recording_config(
            device_index=0,
            channels=10,  # More than device supports
            sample_rate=16000
        )

        assert result['valid'] is False

    def test_record_success(self, mock_audio_manager):
        """Test successful recording"""
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        assert filename is not None
        assert os.path.exists(filename)

    def test_record_with_progress_callback(self, mock_audio_manager):
        """Test recording with progress callback"""
        progress_values = []

        def callback(progress):
            progress_values.append(progress)

        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test',
            progress_callback=callback
        )

        assert len(progress_values) > 0
        assert progress_values[-1] == 100

    def test_record_failure(self, mock_audio_manager):
        """Test recording failure"""
        mock_audio_manager.set_should_fail(True)

        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        assert filename is None

    def test_get_file_info(self, mock_audio_manager):
        """Test getting file information"""
        # First create a recording
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        file_info = mock_audio_manager.get_file_info(filename)

        assert 'filename' in file_info
        assert 'file_size' in file_info
        assert 'file_hash' in file_info
        assert file_info['file_size'] > 0

    def test_get_file_info_nonexistent(self, mock_audio_manager):
        """Test getting info for non-existent file"""
        file_info = mock_audio_manager.get_file_info('/nonexistent/file.wav')

        assert file_info == {}

    def test_file_hash_consistency(self, mock_audio_manager):
        """Test that file hash is consistent"""
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        info1 = mock_audio_manager.get_file_info(filename)
        info2 = mock_audio_manager.get_file_info(filename)

        assert info1['file_hash'] == info2['file_hash']


class TestMockSoundDevice:
    """Tests for MockSoundDevice"""

    def test_query_all_devices(self, mock_sounddevice: MockSoundDevice):
        """Test querying all devices"""
        devices = mock_sounddevice.query_devices()

        assert len(devices) >= 1

    def test_query_input_devices(self, mock_sounddevice: MockSoundDevice):
        """Test querying input devices only"""
        devices = mock_sounddevice.query_devices(kind='input')

        for device in devices:
            assert device['max_input_channels'] > 0

    def test_query_specific_device(self, mock_sounddevice: MockSoundDevice):
        """Test querying a specific device by index"""
        device = mock_sounddevice.query_devices(device=0)

        assert 'name' in device
        assert 'index' in device

    def test_query_invalid_device(self, mock_sounddevice: MockSoundDevice):
        """Test querying invalid device index"""
        with pytest.raises(ValueError):
            mock_sounddevice.query_devices(device=999)

    def test_add_device(self, mock_sounddevice: MockSoundDevice):
        """Test adding a mock device"""
        initial_count = len(mock_sounddevice.query_devices())

        mock_sounddevice.add_device(MockAudioDevice(
            index=5,
            name='New Test Device',
            max_input_channels=4
        ))

        devices = mock_sounddevice.query_devices()
        assert len(devices) == initial_count + 1

    def test_rec_function(self, mock_sounddevice: MockSoundDevice):
        """Test mock rec function"""
        data = mock_sounddevice.rec(
            frames=16000,
            samplerate=16000,
            channels=1,
            blocking=True
        )

        assert data is not None
        assert data.shape == (16000, 1)

    def test_rec_with_error(self, mock_sounddevice: MockSoundDevice):
        """Test rec function with simulated error"""
        mock_sounddevice.set_recording_error(RuntimeError("Audio device error"))

        with pytest.raises(RuntimeError):
            mock_sounddevice.rec(
                frames=16000,
                samplerate=16000,
                channels=1,
                blocking=True
            )


class TestAudioFileFormats:
    """Tests for audio file format handling"""

    def test_wav_file_created(self, mock_audio_manager):
        """Test that WAV file is created correctly"""
        import wave

        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        # Verify it's a valid WAV file
        with wave.open(filename, 'rb') as wav:
            assert wav.getnchannels() == 1
            assert wav.getframerate() == 16000

    def test_stereo_recording(self, mock_audio_manager):
        """Test stereo recording"""
        import wave

        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=2,
            device_index=0,
            device_name='test'
        )

        with wave.open(filename, 'rb') as wav:
            assert wav.getnchannels() == 2
