"""
Mock Audio modules for testing without real audio hardware
"""
import os
import time
import hashlib
import tempfile
import numpy as np
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class MockAudioDevice:
    """Mock audio device information"""
    index: int
    name: str
    max_input_channels: int = 2
    max_output_channels: int = 0
    default_samplerate: float = 44100.0
    hostapi: int = 0


class MockSoundDevice:
    """
    Mock sounddevice module for testing

    Usage:
        mock_sd = MockSoundDevice()
        # Patch sounddevice with mock_sd
        mock_sd.add_device(MockAudioDevice(index=0, name='Test Mic'))
    """

    def __init__(self):
        self._devices: List[MockAudioDevice] = []
        self._recording_data: Optional[np.ndarray] = None
        self._is_recording = False
        self._recording_error: Optional[Exception] = None

        # Add default device
        self._devices.append(MockAudioDevice(
            index=0,
            name='Mock Audio Input Device',
            max_input_channels=2,
            default_samplerate=16000.0
        ))

    def add_device(self, device: MockAudioDevice):
        """Add a mock audio device"""
        self._devices.append(device)

    def clear_devices(self):
        """Clear all mock devices"""
        self._devices.clear()

    def query_devices(self, device=None, kind=None):
        """Mock query_devices function"""
        if device is not None:
            if isinstance(device, int):
                for d in self._devices:
                    if d.index == device:
                        return {
                            'name': d.name,
                            'index': d.index,
                            'max_input_channels': d.max_input_channels,
                            'max_output_channels': d.max_output_channels,
                            'default_samplerate': d.default_samplerate,
                            'hostapi': d.hostapi
                        }
                raise ValueError(f"Invalid device index: {device}")
            return self.query_devices()

        # Return all devices
        result = []
        for d in self._devices:
            result.append({
                'name': d.name,
                'index': d.index,
                'max_input_channels': d.max_input_channels,
                'max_output_channels': d.max_output_channels,
                'default_samplerate': d.default_samplerate,
                'hostapi': d.hostapi
            })

        if kind == 'input':
            result = [d for d in result if d['max_input_channels'] > 0]

        return result

    def set_recording_error(self, error: Exception):
        """Set an error to be raised during recording"""
        self._recording_error = error

    def clear_recording_error(self):
        """Clear the recording error"""
        self._recording_error = None

    def rec(self, frames: int, samplerate: int, channels: int,
            dtype: str = 'float32', device: int = None,
            blocking: bool = True):
        """Mock rec function"""
        if self._recording_error:
            raise self._recording_error

        self._is_recording = True

        # Generate mock audio data (silence with some noise)
        duration = frames / samplerate
        data = np.random.randn(frames, channels).astype(dtype) * 0.01

        if blocking:
            # Simulate recording time (but faster for tests)
            time.sleep(min(duration * 0.1, 1.0))  # Cap at 1 second for tests
            self._is_recording = False

        self._recording_data = data
        return data

    def wait(self):
        """Mock wait function"""
        while self._is_recording:
            time.sleep(0.01)

    @property
    def default(self):
        """Mock default device property"""
        class DefaultDevice:
            device = (0, None)  # (input, output)
        return DefaultDevice()


class MockAudioManager:
    """
    Mock AudioManager for testing

    Provides the same interface as the real AudioManager
    """

    def __init__(self, temp_dir: str = 'temp_wav'):
        self.temp_dir = temp_dir
        self.mock_sd = MockSoundDevice()
        self._recorded_files: List[str] = []
        self._should_fail = False
        self._progress_callback: Optional[Callable] = None

        # Create temp directory
        os.makedirs(temp_dir, exist_ok=True)

    def set_should_fail(self, should_fail: bool):
        """Set whether recording should fail"""
        self._should_fail = should_fail

    def list_devices(self) -> List[Dict[str, Any]]:
        """List available audio devices"""
        return self.mock_sd.query_devices(kind='input')

    def list_devices_as_dict(self) -> List[Dict[str, Any]]:
        """List devices as dictionary format"""
        devices = self.list_devices()
        return [
            {
                'index': d['index'],
                'name': d['name'],
                'max_input_channels': d['max_input_channels'],
                'default_samplerate': d['default_samplerate']
            }
            for d in devices
        ]

    def validate_recording_config(self, device_index: int, channels: int,
                                   sample_rate: int) -> Dict[str, Any]:
        """Validate recording configuration"""
        devices = self.list_devices()

        if not devices:
            return {
                'valid': False,
                'error': 'No audio input devices found'
            }

        # Check device index
        device_indices = [d['index'] for d in devices]
        if device_index not in device_indices:
            return {
                'valid': False,
                'error': f'Invalid device index: {device_index}'
            }

        # Check channels
        device = next(d for d in devices if d['index'] == device_index)
        if channels > device['max_input_channels']:
            return {
                'valid': False,
                'error': f'Device only supports {device["max_input_channels"]} channels'
            }

        return {'valid': True}

    def record(self, duration: int, sample_rate: int = 16000,
               channels: int = 1, device_index: int = 0,
               device_name: str = 'test', bit_depth: int = 16,
               progress_callback: Callable = None) -> Optional[str]:
        """
        Mock recording function

        Returns:
            Filename if successful, None if failed
        """
        if self._should_fail:
            return None

        self._progress_callback = progress_callback

        # Simulate progress
        total_steps = 10
        for i in range(total_steps):
            time.sleep(0.05)  # Small delay for testing
            if progress_callback:
                try:
                    progress_callback(int((i + 1) / total_steps * 100))
                except Exception:
                    # Ignore callback errors, continue recording
                    pass

        # Generate mock WAV file
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(self.temp_dir, f'{device_name}_{timestamp}.wav')

        # Create a simple WAV file
        self._create_mock_wav(filename, duration, sample_rate, channels)
        self._recorded_files.append(filename)

        return filename

    def _create_mock_wav(self, filename: str, duration: int,
                         sample_rate: int, channels: int):
        """Create a mock WAV file for testing"""
        import wave
        import struct

        # Generate silence data
        num_samples = duration * sample_rate
        data = b'\x00\x00' * num_samples * channels

        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(data)

    def get_file_info(self, filename: str) -> Dict[str, Any]:
        """Get information about a recorded file"""
        if not os.path.exists(filename):
            return {}

        file_size = os.path.getsize(filename)

        # Calculate hash
        with open(filename, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        return {
            'filename': os.path.basename(filename),
            'file_path': filename,
            'file_size': file_size,
            'file_hash': file_hash,
            'actual_duration': 10  # Mock duration
        }

    def cleanup(self):
        """Clean up recorded files"""
        for f in self._recorded_files:
            if os.path.exists(f):
                os.remove(f)
        self._recorded_files.clear()
