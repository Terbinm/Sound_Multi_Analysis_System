"""
Edge Client Main Module

Multi-backend edge client for audio recording and uploading.
Supports command aggregation and result broadcasting across multiple backends.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from audio_manager import AudioManager
from config_manager import ConfigManager
from logger_manager import LoggerManager
from multi_backend_manager import MultiBackendManager
from storage_cleaner import CleanupTarget, StorageCleaner

logger = logging.getLogger(__name__)


class EdgeClient:
    """Edge client with multi-backend support"""

    def __init__(self, config_path: str = 'device_config.json'):
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load()

        # Initialize audio manager
        self.audio_manager = AudioManager(temp_dir=self.config.temp_wav_dir)

        # Initialize multi-backend manager
        self.backends = MultiBackendManager(
            backends=self.config.backends,
            config=self.config.multi_backend,
            device_id=self.config.device_id or "",
            device_name=self.config.device_name
        )

        # Set command handlers
        self.backends.on_record = self._handle_record
        self.backends.on_stop = self._handle_stop
        self.backends.on_query_audio_devices = self._handle_query_devices
        self.backends.on_update_config = self._handle_update_config

        # State
        self.status = 'IDLE'
        self.current_recording_uuid: str | None = None
        self._heartbeat_thread = None
        self._heartbeat_stop = None

        logger.info(
            f"EdgeClient initialized: device_id={self.config.device_id}, "
            f"backends={len(self.config.backends)}"
        )

    def _handle_record(self, data: dict):
        """Handle recording command"""
        if self.status == 'RECORDING':
            logger.warning("Already recording, ignoring command")
            return

        # Parse parameters
        duration = data.get('duration', 10)
        channels = data.get('channels', self.config.audio_config.channels)
        sample_rate = data.get('sample_rate', self.config.audio_config.sample_rate)
        device_index = data.get('device_index', self.config.audio_config.default_device_index)
        recording_uuid = data.get('recording_uuid')

        # Update state
        self.status = 'RECORDING'
        self.current_recording_uuid = recording_uuid

        # Broadcast recording started
        self.backends.broadcast('edge.recording_started', {
            'device_id': self.config.device_id,
            'recording_uuid': recording_uuid
        })

        try:
            # Progress callback
            def on_progress(percent: int):
                self.backends.broadcast('edge.recording_progress', {
                    'device_id': self.config.device_id,
                    'recording_uuid': recording_uuid,
                    'progress_percent': percent
                })

            # Record audio
            logger.info(
                f"Recording: duration={duration}s, channels={channels}, "
                f"rate={sample_rate}, device={device_index}"
            )

            filename = self.audio_manager.record(
                duration=duration,
                sample_rate=sample_rate,
                channels=channels,
                device_index=device_index,
                device_name=self.config.device_name,
                progress_callback=on_progress
            )

            if filename:
                file_info = self.audio_manager.get_file_info(filename)
                logger.info(f"Recording complete: {filename}")

                # Broadcast completion
                self.backends.broadcast('edge.recording_completed', {
                    'device_id': self.config.device_id,
                    'recording_uuid': recording_uuid,
                    'filename': file_info.get('filename'),
                    'file_size': file_info.get('file_size'),
                    'file_hash': file_info.get('file_hash'),
                    'actual_duration': file_info.get('actual_duration')
                })

                # Upload to all backends
                self._upload_recording(filename, duration, recording_uuid)
            else:
                logger.error("Recording failed")
                self.backends.broadcast('edge.recording_failed', {
                    'device_id': self.config.device_id,
                    'recording_uuid': recording_uuid,
                    'error': 'Recording failed'
                })

        except Exception as e:
            logger.error(f"Recording error: {e}", exc_info=True)
            self.backends.broadcast('edge.recording_failed', {
                'device_id': self.config.device_id,
                'recording_uuid': recording_uuid,
                'error': str(e)
            })

        finally:
            self.status = 'IDLE'
            self.current_recording_uuid = None

    def _handle_stop(self, data: dict):
        """Handle stop command"""
        logger.warning("Stop command not supported (blocking recording)")

    def _handle_query_devices(self, data: dict):
        """Handle audio device query"""
        request_id = data.get('request_id')
        devices = self.audio_manager.list_devices_as_dict()

        self.backends.broadcast('edge.audio_devices_response', {
            'device_id': self.config.device_id,
            'request_id': request_id,
            'devices': devices
        })
        logger.info(f"Responded with {len(devices)} audio devices")

    def _handle_update_config(self, data: dict):
        """Handle configuration update"""
        if 'device_name' in data:
            self.config.device_name = data['device_name']

        if 'audio_config' in data:
            audio = data['audio_config']
            if 'default_device_index' in audio:
                self.config.audio_config.default_device_index = audio['default_device_index']
            if 'channels' in audio:
                self.config.audio_config.channels = audio['channels']
            if 'sample_rate' in audio:
                self.config.audio_config.sample_rate = audio['sample_rate']
            if 'bit_depth' in audio:
                self.config.audio_config.bit_depth = audio['bit_depth']

        self.config_manager.save()
        logger.info("Configuration updated")

    def _upload_recording(self, filename: str, duration: float, recording_uuid: str | None):
        """Upload recording to all backends"""
        metadata = {
            'duration': duration,
            'device_id': self.config.device_id,
            'recording_uuid': recording_uuid or '',
        }

        file_info = self.audio_manager.get_file_info(filename)
        metadata['file_size'] = file_info.get('file_size', 0)
        metadata['file_hash'] = file_info.get('file_hash', '')

        results = self.backends.upload_to_all(filename, metadata)

        successful = [bid for bid, ok in results.items() if ok]
        if successful:
            logger.info(f"Upload complete to: {successful}")
        else:
            logger.error("Upload failed to all backends")

    def _start_heartbeat(self):
        """Start heartbeat thread"""
        import threading

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return

        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="Heartbeat"
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        """Stop heartbeat thread"""
        if self._heartbeat_stop:
            self._heartbeat_stop.set()

    def _heartbeat_loop(self):
        """Heartbeat loop"""
        time.sleep(1)  # Initial delay

        while self._heartbeat_stop and not self._heartbeat_stop.is_set():
            if self.backends.has_any_connection():
                self.backends.broadcast('edge.heartbeat', {
                    'device_id': self.config.device_id,
                    'status': self.status,
                    'current_recording': self.current_recording_uuid,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })

            self._heartbeat_stop.wait(self.config.heartbeat_interval)

    def run(self):
        """Main run loop"""
        while True:
            try:
                # Connect to all backends
                results = self.backends.connect_all()
                connected = [bid for bid, ok in results.items() if ok]

                if connected:
                    logger.info(f"Connected to backends: {connected}")
                    self._start_heartbeat()
                else:
                    logger.warning("Failed to connect to any backend")

                # Monitor loop
                while True:
                    time.sleep(5)

                    if not self.backends.has_any_connection():
                        logger.warning("All backends disconnected")
                        break

            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break

            except Exception as e:
                logger.error(f"Main loop error: {e}", exc_info=True)

            # Cleanup and retry
            self._stop_heartbeat()
            self.backends.disconnect_all()
            logger.info(f"Retrying in {self.config.reconnect_delay}s...")
            time.sleep(self.config.reconnect_delay)

    def close(self):
        """Cleanup and close"""
        self._stop_heartbeat()
        self.backends.disconnect_all()
        logger.info("EdgeClient closed")


def main():
    """Main entry point"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'device_config.json')

    # Load config first for logging setup
    config_manager = ConfigManager(config_path)
    config = config_manager.load()

    # Initialize logging
    LoggerManager.setup(config.logging_config, base_dir=script_dir)
    logger.info("Logging initialized")

    # Initialize storage cleaner
    cleaner: StorageCleaner | None = None
    if config.storage_cleanup.enabled:
        cleaner = StorageCleaner()

        # Add temp_wav cleanup target
        temp_wav_dir = os.path.join(script_dir, config.temp_wav_dir)
        cleaner.add_target(CleanupTarget(
            name='temp_wav',
            directory=temp_wav_dir,
            max_size_gb=config.storage_cleanup.temp_wav_max_gb,
            file_patterns=['*.wav']
        ))

        # Add logs cleanup target
        log_dir = os.path.join(script_dir, config.logging_config.log_dir)
        cleaner.add_target(CleanupTarget(
            name='logs',
            directory=log_dir,
            max_size_gb=config.storage_cleanup.logs_max_gb,
            file_patterns=['*.log', '*.log.gz', '*.log.*']
        ))

        # Start scheduler (check every hour)
        interval = int(config.storage_cleanup.check_interval_hours * 3600)
        cleaner.start(interval_seconds=interval)
        logger.info(f"Storage cleaner started (interval: {interval}s)")

    # Create and run client
    client = EdgeClient(config_path)

    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if cleaner:
            cleaner.stop()
        client.close()


if __name__ == "__main__":
    main()
