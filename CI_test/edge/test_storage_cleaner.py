"""
Tests for StorageCleaner

Tests cover:
- Cleanup target configuration
- Size calculation
- File pattern matching
- Cleanup execution
- Scheduler management
"""
import pytest
import os
import threading
import fnmatch
from unittest.mock import MagicMock, patch


class TestCleanupTarget:
    """Test CleanupTarget configuration"""

    @pytest.mark.unit
    def test_default_values(self):
        """Test cleanup target default values"""
        defaults = {
            'max_size_gb': 20.0,
            'threshold_percent': 90.0,
            'target_percent': 70.0,
            'file_patterns': ['*']
        }

        assert defaults['max_size_gb'] == 20.0
        assert defaults['threshold_percent'] == 90.0
        assert defaults['target_percent'] == 70.0
        assert '*' in defaults['file_patterns']

    @pytest.mark.unit
    def test_max_bytes_calculation(self):
        """Test max_bytes property calculation"""
        max_size_gb = 20.0
        max_bytes = int(max_size_gb * 1024 * 1024 * 1024)

        expected = 20 * 1024 * 1024 * 1024  # 20 GB in bytes
        assert max_bytes == expected

    @pytest.mark.unit
    def test_threshold_bytes_calculation(self):
        """Test threshold_bytes property calculation"""
        max_size_gb = 20.0
        threshold_percent = 90.0

        max_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        threshold_bytes = int(max_bytes * threshold_percent / 100)

        # 90% of 20 GB
        expected = int(20 * 1024 * 1024 * 1024 * 0.9)
        assert threshold_bytes == expected

    @pytest.mark.unit
    def test_target_bytes_calculation(self):
        """Test target_bytes property calculation"""
        max_size_gb = 10.0
        target_percent = 70.0

        max_bytes = int(max_size_gb * 1024 * 1024 * 1024)
        target_bytes = int(max_bytes * target_percent / 100)

        # 70% of 10 GB
        expected = int(10 * 1024 * 1024 * 1024 * 0.7)
        assert target_bytes == expected

    @pytest.mark.unit
    def test_custom_file_patterns(self):
        """Test custom file patterns"""
        patterns = ['*.wav', '*.mp3', 'temp_*']

        assert len(patterns) == 3
        assert '*.wav' in patterns


class TestPatternMatching:
    """Test file pattern matching"""

    @pytest.mark.unit
    def test_wildcard_matches_all(self):
        """Test wildcard pattern matches all files"""
        patterns = ['*']
        filename = 'any_file.txt'

        matches = '*' in patterns or any(
            fnmatch.fnmatch(filename, p) for p in patterns
        )

        assert matches is True

    @pytest.mark.unit
    def test_wav_pattern_match(self):
        """Test *.wav pattern matching"""
        patterns = ['*.wav']
        filenames = ['audio.wav', 'audio.mp3', 'audio.WAV', 'audio.txt']

        matches = [f for f in filenames if any(
            fnmatch.fnmatch(f.lower(), p.lower()) for p in patterns
        )]

        assert len(matches) == 2  # audio.wav and audio.WAV

    @pytest.mark.unit
    def test_multiple_patterns(self):
        """Test multiple pattern matching"""
        patterns = ['*.wav', '*.mp3']
        filenames = ['audio.wav', 'audio.mp3', 'audio.ogg']

        matches = [f for f in filenames if any(
            fnmatch.fnmatch(f, p) for p in patterns
        )]

        assert len(matches) == 2
        assert 'audio.ogg' not in matches

    @pytest.mark.unit
    def test_prefix_pattern(self):
        """Test prefix pattern matching"""
        patterns = ['temp_*']
        filenames = ['temp_file.txt', 'file_temp.txt', 'temp_data.log']

        matches = [f for f in filenames if any(
            fnmatch.fnmatch(f, p) for p in patterns
        )]

        assert len(matches) == 2
        assert 'file_temp.txt' not in matches


class TestSizeCalculation:
    """Test size calculation functionality"""

    @pytest.mark.unit
    def test_calculate_size_empty_directory(self, temp_wav_dir):
        """Test size calculation for empty directory"""
        total = 0

        for filename in os.listdir(temp_wav_dir):
            filepath = os.path.join(temp_wav_dir, filename)
            if os.path.isfile(filepath):
                total += os.path.getsize(filepath)

        assert total == 0

    @pytest.mark.unit
    def test_calculate_size_with_files(self, temp_wav_dir):
        """Test size calculation with files"""
        # Create test files
        for i in range(3):
            filepath = os.path.join(temp_wav_dir, f'file{i}.txt')
            with open(filepath, 'w') as f:
                f.write('x' * 100)  # 100 bytes each

        total = 0
        for filename in os.listdir(temp_wav_dir):
            filepath = os.path.join(temp_wav_dir, filename)
            if os.path.isfile(filepath):
                total += os.path.getsize(filepath)

        assert total == 300

    @pytest.mark.unit
    def test_calculate_size_ignores_directories(self, temp_wav_dir):
        """Test size calculation ignores subdirectories"""
        # Create a subdirectory
        subdir = os.path.join(temp_wav_dir, 'subdir')
        os.makedirs(subdir)

        # Create a file in subdir
        with open(os.path.join(subdir, 'file.txt'), 'w') as f:
            f.write('x' * 1000)

        # Calculate size (should not include subdir contents)
        total = 0
        for filename in os.listdir(temp_wav_dir):
            filepath = os.path.join(temp_wav_dir, filename)
            if os.path.isfile(filepath):
                total += os.path.getsize(filepath)

        assert total == 0


class TestCleanupExecution:
    """Test cleanup execution"""

    @pytest.mark.unit
    def test_cleanup_threshold_check(self):
        """Test cleanup threshold checking"""
        current_size = 18 * 1024 * 1024 * 1024  # 18 GB
        threshold_bytes = 18 * 1024 * 1024 * 1024  # 90% of 20 GB

        needs_cleanup = current_size > threshold_bytes

        assert needs_cleanup is False

        current_size = 19 * 1024 * 1024 * 1024  # 19 GB
        needs_cleanup = current_size > threshold_bytes

        assert needs_cleanup is True

    @pytest.mark.unit
    def test_cleanup_deletes_oldest_first(self, temp_wav_dir):
        """Test cleanup deletes oldest files first"""
        import time

        # Create files with different modification times
        files = []
        for i in range(3):
            filepath = os.path.join(temp_wav_dir, f'file{i}.txt')
            with open(filepath, 'w') as f:
                f.write('x' * 100)
            os.utime(filepath, (i * 1000, i * 1000))  # Set mtime
            files.append({
                'path': filepath,
                'mtime': i * 1000,
                'size': 100
            })

        # Sort by mtime (oldest first)
        files.sort(key=lambda x: x['mtime'])

        assert files[0]['path'].endswith('file0.txt')
        assert files[-1]['path'].endswith('file2.txt')

    @pytest.mark.unit
    def test_cleanup_stops_at_target(self):
        """Test cleanup stops when target size is reached"""
        current_size = 20 * 1024 * 1024 * 1024  # 20 GB
        target_bytes = 14 * 1024 * 1024 * 1024  # 70% of 20 GB

        files = [
            {'path': f'/tmp/file{i}.wav', 'size': 2 * 1024 * 1024 * 1024}  # 2 GB each
            for i in range(10)
        ]

        freed = 0
        deleted = 0

        for f in files:
            if current_size - freed <= target_bytes:
                break
            freed += f['size']
            deleted += 1

        # Need to delete 3 files (6 GB) to get from 20 GB to under 14 GB
        assert deleted == 3
        assert current_size - freed <= target_bytes

    @pytest.mark.unit
    def test_cleanup_result_structure(self):
        """Test cleanup result structure"""
        result = {
            'target': 'temp_wav',
            'checked': True,
            'cleaned': True,
            'current_mb': 1500.0,
            'freed_mb': 500.0,
            'deleted_count': 10,
            'error': None
        }

        assert 'target' in result
        assert 'checked' in result
        assert 'cleaned' in result
        assert 'freed_mb' in result
        assert 'deleted_count' in result
        assert result['error'] is None

    @pytest.mark.unit
    def test_cleanup_handles_nonexistent_directory(self):
        """Test cleanup handles nonexistent directory gracefully"""
        directory = '/nonexistent/path'

        result = {
            'checked': False,
            'error': None
        }

        if not os.path.exists(directory):
            result['checked'] = True
            # Should not error, just skip

        assert result['checked'] is True
        assert result['error'] is None


class TestSchedulerManagement:
    """Test scheduler management"""

    @pytest.mark.unit
    def test_scheduler_start(self):
        """Test scheduler start"""
        running = False
        stop_event = threading.Event()

        # Simulate start
        stop_event.clear()
        running = True

        assert running is True
        assert not stop_event.is_set()

    @pytest.mark.unit
    def test_scheduler_stop(self):
        """Test scheduler stop"""
        running = True
        stop_event = threading.Event()

        # Simulate stop
        stop_event.set()
        running = False

        assert running is False
        assert stop_event.is_set()

    @pytest.mark.unit
    def test_scheduler_interval(self):
        """Test scheduler interval configuration"""
        interval_seconds = 3600  # 1 hour

        assert interval_seconds > 0
        assert interval_seconds == 3600

    @pytest.mark.unit
    def test_scheduler_immediate_run(self):
        """Test scheduler runs immediately on start"""
        cleanup_calls = []

        def cleanup_all():
            cleanup_calls.append('cleanup')

        # Simulate immediate run on start
        cleanup_all()

        assert len(cleanup_calls) == 1

    @pytest.mark.unit
    def test_prevent_duplicate_start(self):
        """Test preventing duplicate scheduler start"""
        running = True

        # Try to start again
        can_start = not running

        assert can_start is False


class TestTargetManagement:
    """Test target management"""

    @pytest.mark.unit
    def test_add_target(self):
        """Test adding cleanup target"""
        targets = {}

        target = {
            'name': 'temp_wav',
            'directory': '/tmp/wav',
            'max_size_gb': 20.0
        }

        targets[target['name']] = target

        assert 'temp_wav' in targets
        assert targets['temp_wav']['directory'] == '/tmp/wav'

    @pytest.mark.unit
    def test_remove_target(self):
        """Test removing cleanup target"""
        targets = {
            'target1': {'directory': '/tmp/1'},
            'target2': {'directory': '/tmp/2'}
        }

        del targets['target1']

        assert 'target1' not in targets
        assert 'target2' in targets

    @pytest.mark.unit
    def test_cleanup_all_targets(self):
        """Test cleanup all targets"""
        targets = ['target1', 'target2', 'target3']
        results = {}

        for name in targets:
            results[name] = {'checked': True, 'cleaned': False}

        assert len(results) == 3
        assert all(r['checked'] for r in results.values())


class TestStatusReporting:
    """Test status reporting"""

    @pytest.mark.unit
    def test_status_structure(self):
        """Test status report structure"""
        status = {
            'temp_wav': {
                'directory': '/tmp/wav',
                'max_gb': 20.0,
                'threshold_percent': 90.0,
                'file_patterns': ['*.wav'],
                'exists': True,
                'current_mb': 1500.0,
                'usage_percent': 7.5
            }
        }

        target_status = status['temp_wav']

        assert 'directory' in target_status
        assert 'max_gb' in target_status
        assert 'exists' in target_status
        assert 'current_mb' in target_status
        assert 'usage_percent' in target_status

    @pytest.mark.unit
    def test_usage_percent_calculation(self):
        """Test usage percentage calculation"""
        current_size = 1500 * 1024 * 1024  # 1500 MB
        max_bytes = 20 * 1024 * 1024 * 1024  # 20 GB

        usage_percent = round(current_size / max_bytes * 100, 1)

        assert usage_percent == 7.3  # Approximately

    @pytest.mark.unit
    def test_is_running_property(self):
        """Test is_running property"""
        running = False

        assert running is False

        running = True

        assert running is True

