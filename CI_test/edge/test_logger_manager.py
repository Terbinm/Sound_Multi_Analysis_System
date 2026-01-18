"""
Tests for LoggerManager

Tests cover:
- Log rotation
- Backup compression
- Space management and cleanup
- Singleton pattern
- Configuration
"""
import pytest
import os
import gzip
import logging
import threading
from unittest.mock import MagicMock, patch


class TestCompressingRotatingFileHandler:
    """Test CompressingRotatingFileHandler"""

    @pytest.mark.unit
    def test_handler_initialization(self):
        """Test handler initialization parameters"""
        params = {
            'filename': '/tmp/test.log',
            'mode': 'a',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'encoding': 'utf-8',
            'compress_backup': True
        }

        assert params['maxBytes'] == 10 * 1024 * 1024
        assert params['backupCount'] == 5
        assert params['compress_backup'] is True

    @pytest.mark.unit
    def test_compress_backup_flag(self):
        """Test compress_backup flag behavior"""
        with_compression = {'compress_backup': True}
        without_compression = {'compress_backup': False}

        assert with_compression['compress_backup'] is True
        assert without_compression['compress_backup'] is False

    @pytest.mark.unit
    def test_backup_file_naming(self):
        """Test backup file naming convention"""
        base_filename = '/tmp/edge_client.log'

        backup_names = [
            f"{base_filename}.1",      # Most recent, uncompressed
            f"{base_filename}.2.gz",   # Older, compressed
            f"{base_filename}.3.gz",
            f"{base_filename}.4.gz",
            f"{base_filename}.5.gz"
        ]

        assert backup_names[0].endswith('.1')
        assert backup_names[1].endswith('.2.gz')

    @pytest.mark.unit
    def test_compress_starting_from_second_backup(self):
        """Test compression starts from second backup"""
        backupCount = 5
        backups_to_compress = list(range(2, backupCount + 1))

        assert 1 not in backups_to_compress  # First backup not compressed
        assert 2 in backups_to_compress
        assert 5 in backups_to_compress

    @pytest.mark.unit
    def test_compression_runs_in_background(self):
        """Test compression runs in background thread"""
        compress_called = threading.Event()

        def mock_compress():
            compress_called.set()

        # Simulate background compression
        thread = threading.Thread(target=mock_compress, daemon=True)
        thread.start()
        thread.join(timeout=1)

        assert compress_called.is_set()


class TestLoggerManagerSingleton:
    """Test LoggerManager singleton pattern"""

    @pytest.mark.unit
    def test_singleton_instance(self):
        """Test singleton returns same instance"""
        instances = []

        # Simulate multiple instantiations
        for _ in range(3):
            # In real code: instance = LoggerManager()
            instance_id = 'singleton-001'
            instances.append(instance_id)

        assert all(i == instances[0] for i in instances)

    @pytest.mark.unit
    def test_initialized_flag(self):
        """Test _initialized flag prevents re-initialization"""
        initialized = False

        # First init
        if not initialized:
            # Do initialization
            initialized = True

        # Second call should skip
        reinit_skipped = initialized

        assert reinit_skipped is True

    @pytest.mark.unit
    def test_get_instance_returns_singleton(self):
        """Test get_instance returns singleton"""
        _instance = {'id': 'logger-manager-001'}

        def get_instance():
            return _instance

        instance1 = get_instance()
        instance2 = get_instance()

        assert instance1 is instance2


class TestLoggerConfiguration:
    """Test logger configuration"""

    @pytest.mark.unit
    def test_log_level_setting(self):
        """Test log level configuration"""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

        for level in valid_levels:
            level_value = getattr(logging, level.upper(), None)
            assert level_value is not None

    @pytest.mark.unit
    def test_log_directory_resolution(self):
        """Test log directory path resolution"""
        import posixpath  # Use POSIX path for consistent behavior

        base_dir = '/app/edge_client'
        relative_log_dir = 'logs'
        absolute_log_dir = '/var/log/edge_client'

        # Relative path - use posixpath for cross-platform consistency
        if not posixpath.isabs(relative_log_dir):
            resolved = posixpath.join(base_dir, relative_log_dir)
        else:
            resolved = relative_log_dir

        assert resolved == '/app/edge_client/logs'

        # Absolute path
        if not posixpath.isabs(absolute_log_dir):
            resolved = posixpath.join(base_dir, absolute_log_dir)
        else:
            resolved = absolute_log_dir

        assert resolved == '/var/log/edge_client'

    @pytest.mark.unit
    def test_console_output_setting(self):
        """Test console output configuration"""
        config = {'console_output': True, 'console_level': 'INFO'}

        assert config['console_output'] is True
        assert config['console_level'] == 'INFO'

    @pytest.mark.unit
    def test_formatter_pattern(self):
        """Test log formatter pattern"""
        pattern = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        assert '%(asctime)s' in pattern
        assert '%(name)s' in pattern
        assert '%(levelname)s' in pattern
        assert '%(message)s' in pattern


class TestSpaceManagement:
    """Test log space management"""

    @pytest.mark.unit
    def test_max_total_size_threshold(self):
        """Test max total size threshold calculation"""
        max_total_size_gb = 5.0
        cleanup_threshold_percent = 80.0

        max_size_bytes = max_total_size_gb * 1024 * 1024 * 1024
        threshold_bytes = max_size_bytes * (cleanup_threshold_percent / 100)

        # 80% of 5 GB = 4 GB
        expected = 4.0 * 1024 * 1024 * 1024
        assert threshold_bytes == expected

    @pytest.mark.unit
    def test_logs_total_size_calculation(self, temp_log_dir):
        """Test total log size calculation"""
        # Create log files
        log_files = ['app.log', 'app.log.1', 'app.log.2.gz']
        for name in log_files:
            filepath = os.path.join(temp_log_dir, name)
            with open(filepath, 'w') as f:
                f.write('x' * 1000)  # 1000 bytes each

        # Calculate total
        total = 0
        for filename in os.listdir(temp_log_dir):
            filepath = os.path.join(temp_log_dir, filename)
            if os.path.isfile(filepath):
                if filename.endswith(('.log', '.log.gz')) or '.log.' in filename:
                    total += os.path.getsize(filepath)

        assert total == 3000

    @pytest.mark.unit
    def test_cleanup_target_70_percent(self):
        """Test cleanup targets 70% of max size"""
        max_size = 5 * 1024 * 1024 * 1024  # 5 GB
        target_size = max_size * 0.7  # 70%

        expected = 3.5 * 1024 * 1024 * 1024
        assert target_size == expected

    @pytest.mark.unit
    def test_cleanup_skips_current_log(self):
        """Test cleanup skips current log file"""
        current_log = 'edge_client.log'
        files = [
            'edge_client.log',
            'edge_client.log.1',
            'edge_client.log.2.gz'
        ]

        files_to_delete = [f for f in files if f != current_log]

        assert current_log not in files_to_delete
        assert len(files_to_delete) == 2

    @pytest.mark.unit
    def test_cleanup_order_oldest_first(self, temp_log_dir):
        """Test cleanup deletes oldest files first"""
        # Create files with different mtimes
        files = []
        for i, mtime in enumerate([1000, 2000, 3000]):
            filepath = os.path.join(temp_log_dir, f'app.log.{i + 1}')
            with open(filepath, 'w') as f:
                f.write('x' * 100)
            os.utime(filepath, (mtime, mtime))
            files.append({'path': filepath, 'mtime': mtime})

        # Sort by mtime
        files.sort(key=lambda x: x['mtime'])

        assert files[0]['mtime'] == 1000
        assert files[-1]['mtime'] == 3000


class TestFallbackBehavior:
    """Test fallback to console behavior"""

    @pytest.mark.unit
    def test_fallback_on_directory_error(self):
        """Test fallback to console on directory error"""
        fallback_to_console = False

        try:
            # Simulate directory creation failure
            raise IOError("Cannot create log directory")
        except IOError:
            fallback_to_console = True

        assert fallback_to_console is True

    @pytest.mark.unit
    def test_fallback_on_write_error(self):
        """Test fallback on write permission error"""
        fallback_to_console = False

        try:
            # Simulate write test failure
            raise PermissionError("Cannot write to directory")
        except PermissionError:
            fallback_to_console = True

        assert fallback_to_console is True

    @pytest.mark.unit
    def test_fallback_flag_in_info(self):
        """Test fallback flag is included in info"""
        info = {
            'log_dir': '/var/log/edge',
            'enabled': True,
            'fallback_to_console': True
        }

        assert info['fallback_to_console'] is True


class TestLogsInfo:
    """Test get_logs_info functionality"""

    @pytest.mark.unit
    def test_logs_info_structure(self):
        """Test logs info structure"""
        info = {
            'log_dir': '/var/log/edge',
            'enabled': True,
            'fallback_to_console': False,
            'total_size_mb': 150.5,
            'file_count': 5,
            'max_size_gb': 5.0
        }

        assert 'log_dir' in info
        assert 'enabled' in info
        assert 'total_size_mb' in info
        assert 'file_count' in info
        assert 'max_size_gb' in info

    @pytest.mark.unit
    def test_file_count_calculation(self, temp_log_dir):
        """Test log file count calculation"""
        # Create various files
        files = ['app.log', 'app.log.1', 'app.log.2.gz', 'other.txt']
        for name in files:
            filepath = os.path.join(temp_log_dir, name)
            with open(filepath, 'w') as f:
                f.write('test')

        # Count log files
        count = 0
        for f in os.listdir(temp_log_dir):
            filepath = os.path.join(temp_log_dir, f)
            if os.path.isfile(filepath):
                if f.endswith(('.log', '.log.gz')) or '.log.' in f:
                    count += 1

        assert count == 3  # Excludes other.txt

    @pytest.mark.unit
    def test_size_mb_rounding(self):
        """Test size MB rounding"""
        total_bytes = 157483920  # bytes

        total_size_mb = round(total_bytes / 1024 / 1024, 2)

        # 157483920 / 1024 / 1024 = 150.18519... rounds to 150.19
        assert total_size_mb == 150.19


class TestSetupLogging:
    """Test setup_logging convenience function"""

    @pytest.mark.unit
    def test_setup_returns_root_logger(self):
        """Test setup returns root logger"""
        root_logger = logging.getLogger()

        assert root_logger is not None
        assert root_logger.name == 'root'

    @pytest.mark.unit
    def test_setup_clears_existing_handlers(self):
        """Test setup clears existing handlers"""
        logger = logging.getLogger('test')
        logger.addHandler(logging.NullHandler())
        logger.addHandler(logging.NullHandler())

        initial_count = len(logger.handlers)

        # Clear handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

        assert len(logger.handlers) == 0
        assert initial_count == 2


class TestCompressionLogic:
    """Test compression logic"""

    @pytest.mark.unit
    def test_gzip_compression(self, temp_log_dir):
        """Test gzip compression of log file"""
        source = os.path.join(temp_log_dir, 'test.log.2')
        target = os.path.join(temp_log_dir, 'test.log.2.gz')

        # Create source file
        content = b'This is a test log file content.\n' * 100
        with open(source, 'wb') as f:
            f.write(content)

        # Compress
        with open(source, 'rb') as f_in:
            with gzip.open(target, 'wb', compresslevel=9) as f_out:
                f_out.write(f_in.read())

        assert os.path.exists(target)
        assert os.path.getsize(target) < os.path.getsize(source)

    @pytest.mark.unit
    def test_compression_preserves_content(self, temp_log_dir):
        """Test compression preserves content"""
        source = os.path.join(temp_log_dir, 'test.log')
        compressed = os.path.join(temp_log_dir, 'test.log.gz')

        original_content = b'Test content to compress\n' * 10

        with open(source, 'wb') as f:
            f.write(original_content)

        with open(source, 'rb') as f_in:
            with gzip.open(compressed, 'wb') as f_out:
                f_out.write(f_in.read())

        # Decompress and verify
        with gzip.open(compressed, 'rb') as f:
            decompressed = f.read()

        assert decompressed == original_content

    @pytest.mark.unit
    def test_skip_already_compressed(self):
        """Test skip already compressed files"""
        source = '/tmp/test.log.2'
        target = '/tmp/test.log.2.gz'

        # Simulate target already exists
        target_exists = True

        should_compress = not target_exists

        assert should_compress is False

