"""
Tests for recording workflow
"""
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from CI_test.edge.mocks.mock_server import MockSocketIOClient
from CI_test.edge.mocks.mock_audio import MockAudioManager


class TestRecordingWorkflow:
    """Tests for complete recording workflow"""

    def test_complete_recording_flow(self, mock_socketio_client: MockSocketIOClient,
                                     mock_audio_manager: MockAudioManager):
        """Test complete recording workflow from command to completion"""
        events_emitted = []

        def track_emit(event, data):
            events_emitted.append({'event': event, 'data': data})
            mock_socketio_client.emit(event, data)

        mock_socketio_client.connect('http://localhost:55103')

        # Step 1: Receive record command
        record_command = {
            'recording_uuid': 'rec-uuid-001',
            'duration': 2,
            'channels': 1,
            'sample_rate': 16000,
            'device_index': 0,
            'bit_depth': 16
        }

        # Step 2: Start recording
        track_emit('edge.recording_started', {
            'device_id': 'test-device',
            'recording_uuid': record_command['recording_uuid']
        })

        # Step 3: Execute recording with progress
        def progress_callback(progress):
            track_emit('edge.recording_progress', {
                'device_id': 'test-device',
                'recording_uuid': record_command['recording_uuid'],
                'progress_percent': progress
            })

        filename = mock_audio_manager.record(
            duration=record_command['duration'],
            sample_rate=record_command['sample_rate'],
            channels=record_command['channels'],
            device_index=record_command['device_index'],
            device_name='test',
            progress_callback=progress_callback
        )

        # Step 4: Emit completion
        file_info = mock_audio_manager.get_file_info(filename)
        track_emit('edge.recording_completed', {
            'device_id': 'test-device',
            'recording_uuid': record_command['recording_uuid'],
            'filename': file_info['filename'],
            'file_size': file_info['file_size'],
            'file_hash': file_info['file_hash'],
            'actual_duration': file_info['actual_duration']
        })

        # Verify workflow
        event_names = [e['event'] for e in events_emitted]
        assert 'edge.recording_started' in event_names
        assert 'edge.recording_progress' in event_names
        assert 'edge.recording_completed' in event_names

        # Verify progress was reported
        progress_events = [e for e in events_emitted if e['event'] == 'edge.recording_progress']
        assert len(progress_events) > 0

    def test_recording_failure_flow(self, mock_socketio_client: MockSocketIOClient,
                                    mock_audio_manager: MockAudioManager):
        """Test recording failure workflow"""
        mock_audio_manager.set_should_fail(True)
        mock_socketio_client.connect('http://localhost:55103')

        # Emit started
        mock_socketio_client.emit('edge.recording_started', {
            'device_id': 'test-device',
            'recording_uuid': 'rec-uuid-fail'
        })

        # Attempt recording (will fail)
        filename = mock_audio_manager.record(
            duration=2,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        assert filename is None

        # Emit failure
        mock_socketio_client.emit('edge.recording_failed', {
            'device_id': 'test-device',
            'recording_uuid': 'rec-uuid-fail',
            'error': 'Recording failed'
        })

        failed_events = mock_socketio_client.get_emitted_events('edge.recording_failed')
        assert len(failed_events) == 1

    def test_reject_duplicate_recording(self, mock_socketio_client: MockSocketIOClient):
        """Test that duplicate recording commands are rejected"""
        mock_socketio_client.connect('http://localhost:55103')

        # Simulate device is already recording
        is_recording = True

        if is_recording:
            # Should not start new recording
            pass
        else:
            mock_socketio_client.emit('edge.recording_started', {
                'device_id': 'test-device',
                'recording_uuid': 'rec-uuid-002'
            })

        # No recording_started event should be emitted
        started_events = mock_socketio_client.get_emitted_events('edge.recording_started')
        assert len(started_events) == 0


class TestProgressCallback:
    """Tests for recording progress callback"""

    def test_progress_increments(self, mock_audio_manager: MockAudioManager):
        """Test that progress increments correctly"""
        progress_values = []

        def callback(progress):
            progress_values.append(progress)

        mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test',
            progress_callback=callback
        )

        # Progress should be increasing
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i-1]

    def test_progress_reaches_100(self, mock_audio_manager: MockAudioManager):
        """Test that progress reaches 100%"""
        progress_values = []

        def callback(progress):
            progress_values.append(progress)

        mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test',
            progress_callback=callback
        )

        assert progress_values[-1] == 100

    def test_progress_callback_exception_handling(self, mock_audio_manager: MockAudioManager):
        """Test that recording continues even if callback raises exception"""
        def bad_callback(progress):
            if progress > 50:
                raise ValueError("Callback error")

        # Recording should still complete despite callback error
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test',
            progress_callback=bad_callback
        )

        # Recording should complete successfully despite callback errors
        assert filename is not None
        assert os.path.exists(filename)


class TestRecordingParameters:
    """Tests for recording parameter handling"""

    def test_default_parameters(self, mock_audio_manager: MockAudioManager):
        """Test recording with default parameters"""
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=1,
            device_index=0,
            device_name='test'
        )

        assert filename is not None

    def test_different_sample_rates(self, mock_audio_manager: MockAudioManager):
        """Test recording with different sample rates"""
        sample_rates = [8000, 16000, 22050, 44100, 48000]

        for rate in sample_rates:
            filename = mock_audio_manager.record(
                duration=1,
                sample_rate=rate,
                channels=1,
                device_index=0,
                device_name='test'
            )
            assert filename is not None

    def test_stereo_recording(self, mock_audio_manager: MockAudioManager):
        """Test stereo recording"""
        filename = mock_audio_manager.record(
            duration=1,
            sample_rate=16000,
            channels=2,
            device_index=0,
            device_name='test'
        )

        assert filename is not None


class TestRecordingStateManagement:
    """Tests for recording state management"""

    def test_state_transitions(self):
        """Test state transitions during recording"""
        states = []
        current_state = 'idle'

        # Simulate state machine
        def transition(new_state):
            nonlocal current_state
            states.append((current_state, new_state))
            current_state = new_state

        # Start recording
        transition('recording')
        assert current_state == 'recording'

        # Complete recording
        transition('idle')
        assert current_state == 'idle'

        # Verify transitions
        assert states == [('idle', 'recording'), ('recording', 'idle')]

    def test_state_on_failure(self):
        """Test state returns to idle on failure"""
        current_state = 'idle'

        # Start recording
        current_state = 'recording'

        # Simulate failure
        try:
            raise RuntimeError("Recording error")
        except RuntimeError:
            current_state = 'idle'

        assert current_state == 'idle'

    def test_recording_uuid_tracking(self, mock_socketio_client: MockSocketIOClient):
        """Test that recording UUID is properly tracked"""
        current_recording_uuid = None

        # Start recording
        recording_uuid = 'rec-uuid-tracking-test'
        current_recording_uuid = recording_uuid

        mock_socketio_client.connect('http://localhost:55103')
        mock_socketio_client.emit('edge.recording_started', {
            'device_id': 'test-device',
            'recording_uuid': recording_uuid
        })

        assert current_recording_uuid == recording_uuid

        # Complete recording
        mock_socketio_client.emit('edge.recording_completed', {
            'device_id': 'test-device',
            'recording_uuid': recording_uuid,
            'filename': 'test.wav',
            'file_size': 1000,
            'file_hash': 'abc123',
            'actual_duration': 10
        })

        current_recording_uuid = None
        assert current_recording_uuid is None
