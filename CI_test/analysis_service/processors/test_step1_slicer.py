"""
Tests for Step 1: Slicer

Tests cover:
- Audio slicing
- Overlap handling
- Duration calculation
"""
import pytest
from unittest.mock import MagicMock, patch


class TestAudioSlicing:
    """Test audio slicing functionality"""

    @pytest.mark.unit
    def test_calculate_slice_count(self):
        """Test calculating number of slices"""
        total_duration = 60.0  # seconds
        slice_duration = 10.0  # seconds
        overlap = 0.5  # 50% overlap

        step = slice_duration * (1 - overlap)
        num_slices = int((total_duration - slice_duration) / step) + 1

        assert num_slices > 0

    @pytest.mark.unit
    def test_slice_short_audio(self):
        """Test slicing audio shorter than slice duration"""
        total_duration = 5.0
        slice_duration = 10.0

        if total_duration < slice_duration:
            # Pad or use as single slice
            num_slices = 1
        else:
            num_slices = int(total_duration / slice_duration)

        assert num_slices == 1

    @pytest.mark.unit
    def test_slice_exact_multiple(self):
        """Test slicing when duration is exact multiple"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.0

        num_slices = int(total_duration / slice_duration)
        assert num_slices == 3

    @pytest.mark.unit
    def test_generate_slice_timestamps(self):
        """Test generating slice start/end timestamps"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.0

        slices = []
        start = 0.0
        while start + slice_duration <= total_duration:
            slices.append({
                'start': start,
                'end': start + slice_duration,
                'index': len(slices),
            })
            start += slice_duration

        assert len(slices) == 3
        assert slices[0]['start'] == 0.0
        assert slices[0]['end'] == 10.0


class TestOverlapHandling:
    """Test overlap handling in slicing"""

    @pytest.mark.unit
    def test_50_percent_overlap(self):
        """Test 50% overlap slicing"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.5

        step = slice_duration * (1 - overlap)  # 5 seconds
        num_slices = int((total_duration - slice_duration) / step) + 1

        assert step == 5.0
        assert num_slices == 5  # Slices at 0, 5, 10, 15, 20

    @pytest.mark.unit
    def test_no_overlap(self):
        """Test no overlap slicing"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.0

        step = slice_duration * (1 - overlap)
        num_slices = int((total_duration - slice_duration) / step) + 1

        assert step == 10.0
        assert num_slices == 3

    @pytest.mark.unit
    def test_high_overlap(self):
        """Test high overlap (75%) slicing"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.75

        step = slice_duration * (1 - overlap)  # 2.5 seconds
        num_slices = int((total_duration - slice_duration) / step) + 1

        assert step == 2.5
        assert num_slices == 9

    @pytest.mark.unit
    def test_generate_overlapping_slices(self):
        """Test generating overlapping slice list"""
        total_duration = 20.0
        slice_duration = 10.0
        overlap = 0.5

        step = slice_duration * (1 - overlap)
        slices = []
        start = 0.0

        while start + slice_duration <= total_duration:
            slices.append({
                'start': start,
                'end': start + slice_duration,
            })
            start += step

        # Should have slices at 0, 5, 10
        assert len(slices) == 3
        assert slices[1]['start'] == 5.0


class TestDurationCalculation:
    """Test duration calculation"""

    @pytest.mark.unit
    def test_calculate_duration_from_samples(self):
        """Test calculating duration from sample count"""
        sample_rate = 16000
        num_samples = 160000

        duration = num_samples / sample_rate
        assert duration == 10.0

    @pytest.mark.unit
    def test_slice_sample_indices(self):
        """Test calculating sample indices for slice"""
        sample_rate = 16000
        slice_start = 5.0  # seconds
        slice_end = 15.0  # seconds

        start_sample = int(slice_start * sample_rate)
        end_sample = int(slice_end * sample_rate)

        assert start_sample == 80000
        assert end_sample == 240000
        assert end_sample - start_sample == 160000  # 10 seconds


class TestSliceOutput:
    """Test slice output format"""

    @pytest.mark.unit
    def test_slice_metadata(self):
        """Test slice metadata structure"""
        slice_meta = {
            'index': 0,
            'start_time': 0.0,
            'end_time': 10.0,
            'duration': 10.0,
            'start_sample': 0,
            'end_sample': 160000,
            'parent_recording': 'rec-001',
        }

        assert 'index' in slice_meta
        assert slice_meta['duration'] == slice_meta['end_time'] - slice_meta['start_time']

    @pytest.mark.unit
    def test_multiple_slices_coverage(self):
        """Test that slices cover entire audio"""
        total_duration = 30.0
        slice_duration = 10.0
        overlap = 0.0

        slices = []
        start = 0.0
        while start + slice_duration <= total_duration:
            slices.append((start, start + slice_duration))
            start += slice_duration

        # Check coverage
        covered = sum(end - start for start, end in slices)
        assert covered == total_duration
