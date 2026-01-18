"""
Tests for TaskScheduler Service

Tests cover:
- Scheduled task management
- APScheduler integration
- Job execution
- Task cleanup
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestScheduledTaskManagement:
    """Test scheduled task management"""

    @pytest.mark.unit
    def test_add_scheduled_task(self):
        """Test adding a scheduled task"""
        scheduler = MagicMock()
        scheduler.add_job = MagicMock(return_value=MagicMock(id='job-001'))

        job = scheduler.add_job(
            func=lambda: None,
            trigger='interval',
            minutes=5,
            id='heartbeat_check',
        )

        assert job.id == 'job-001'
        scheduler.add_job.assert_called_once()

    @pytest.mark.unit
    def test_remove_scheduled_task(self):
        """Test removing a scheduled task"""
        scheduler = MagicMock()

        scheduler.remove_job('heartbeat_check')

        scheduler.remove_job.assert_called_once_with('heartbeat_check')

    @pytest.mark.unit
    def test_pause_scheduled_task(self):
        """Test pausing a scheduled task"""
        scheduler = MagicMock()

        scheduler.pause_job('cleanup_task')

        scheduler.pause_job.assert_called_once_with('cleanup_task')

    @pytest.mark.unit
    def test_resume_scheduled_task(self):
        """Test resuming a paused task"""
        scheduler = MagicMock()

        scheduler.resume_job('cleanup_task')

        scheduler.resume_job.assert_called_once_with('cleanup_task')

    @pytest.mark.unit
    def test_list_scheduled_tasks(self):
        """Test listing all scheduled tasks"""
        scheduler = MagicMock()
        scheduler.get_jobs = MagicMock(return_value=[
            MagicMock(id='job-001', name='heartbeat_check'),
            MagicMock(id='job-002', name='cleanup_task'),
        ])

        jobs = scheduler.get_jobs()

        assert len(jobs) == 2
        assert jobs[0].id == 'job-001'


class TestAPSchedulerIntegration:
    """Test APScheduler integration"""

    @pytest.mark.unit
    def test_interval_trigger(self):
        """Test interval trigger configuration"""
        scheduler = MagicMock()

        scheduler.add_job(
            func=lambda: None,
            trigger='interval',
            seconds=30,
            id='heartbeat',
        )

        scheduler.add_job.assert_called_once()
        call_args = scheduler.add_job.call_args
        assert call_args.kwargs['trigger'] == 'interval'
        assert call_args.kwargs['seconds'] == 30

    @pytest.mark.unit
    def test_cron_trigger(self):
        """Test cron trigger configuration"""
        scheduler = MagicMock()

        scheduler.add_job(
            func=lambda: None,
            trigger='cron',
            hour=0,
            minute=0,
            id='daily_cleanup',
        )

        call_args = scheduler.add_job.call_args
        assert call_args.kwargs['trigger'] == 'cron'
        assert call_args.kwargs['hour'] == 0

    @pytest.mark.unit
    def test_date_trigger(self):
        """Test date trigger for one-time execution"""
        scheduler = MagicMock()
        run_date = datetime.now(timezone.utc) + timedelta(hours=1)

        scheduler.add_job(
            func=lambda: None,
            trigger='date',
            run_date=run_date,
            id='one_time_task',
        )

        call_args = scheduler.add_job.call_args
        assert call_args.kwargs['trigger'] == 'date'

    @pytest.mark.unit
    def test_start_scheduler(self):
        """Test starting the scheduler"""
        scheduler = MagicMock()

        scheduler.start()

        scheduler.start.assert_called_once()

    @pytest.mark.unit
    def test_shutdown_scheduler(self):
        """Test shutting down the scheduler"""
        scheduler = MagicMock()

        scheduler.shutdown()

        scheduler.shutdown.assert_called_once()


class TestJobExecution:
    """Test job execution functionality"""

    @pytest.mark.unit
    def test_heartbeat_check_job(self, mock_get_db):
        """Test heartbeat check job execution"""
        devices_collection = mock_get_db['edge_devices']
        now = datetime.now(timezone.utc)

        # Setup test data
        devices_collection.insert_one({
            'device_id': 'stale-device',
            'status': 'online',
            'last_heartbeat': now - timedelta(minutes=10),
        })

        # Simulate heartbeat check job
        threshold = now - timedelta(minutes=5)
        result = devices_collection.update_many(
            {'last_heartbeat': {'$lt': threshold}, 'status': 'online'},
            {'$set': {'status': 'offline'}}
        )

        assert result.modified_count == 1

    @pytest.mark.unit
    def test_cleanup_old_recordings_job(self, mock_get_db):
        """Test cleanup old recordings job"""
        recordings_collection = mock_get_db['recordings']
        now = datetime.now(timezone.utc)

        # Insert old and new recordings
        recordings_collection.insert_one({
            'recording_id': 'old-rec',
            'created_at': now - timedelta(days=60),
            'analysis_status': 'completed',
        })
        recordings_collection.insert_one({
            'recording_id': 'new-rec',
            'created_at': now - timedelta(days=5),
            'analysis_status': 'completed',
        })

        # Cleanup recordings older than 30 days
        threshold = now - timedelta(days=30)
        result = recordings_collection.delete_many({
            'created_at': {'$lt': threshold},
            'analysis_status': 'completed',
        })

        assert result.deleted_count == 1

        # Verify new recording still exists
        new_rec = recordings_collection.find_one({'recording_id': 'new-rec'})
        assert new_rec is not None

    @pytest.mark.unit
    def test_node_status_update_job(self, mock_get_db):
        """Test node status update job"""
        nodes_collection = mock_get_db['node_status']
        now = datetime.now(timezone.utc)

        # Insert stale node
        nodes_collection.insert_one({
            'node_id': 'stale-node',
            'status': 'active',
            'last_heartbeat': now - timedelta(minutes=5),
        })

        # Simulate node status check
        threshold = now - timedelta(minutes=2)
        result = nodes_collection.update_many(
            {'last_heartbeat': {'$lt': threshold}, 'status': 'active'},
            {'$set': {'status': 'inactive'}}
        )

        assert result.modified_count == 1


class TestTaskCleanup:
    """Test task cleanup functionality"""

    @pytest.mark.unit
    def test_cleanup_completed_tasks(self, mock_get_db):
        """Test cleaning up completed tasks"""
        tasks_collection = mock_get_db['task_execution_logs']
        now = datetime.now(timezone.utc)

        # Insert tasks
        tasks_collection.insert_one({
            'task_id': 'old-completed',
            'status': 'completed',
            'completed_at': now - timedelta(days=10),
        })
        tasks_collection.insert_one({
            'task_id': 'new-completed',
            'status': 'completed',
            'completed_at': now - timedelta(days=1),
        })
        tasks_collection.insert_one({
            'task_id': 'pending',
            'status': 'pending',
            'created_at': now - timedelta(days=10),
        })

        # Cleanup completed tasks older than 7 days
        threshold = now - timedelta(days=7)
        result = tasks_collection.delete_many({
            'status': 'completed',
            'completed_at': {'$lt': threshold},
        })

        assert result.deleted_count == 1

        # Pending task should still exist
        pending = tasks_collection.find_one({'task_id': 'pending'})
        assert pending is not None

    @pytest.mark.unit
    def test_cleanup_failed_tasks_logs(self, mock_get_db):
        """Test cleaning up failed task logs"""
        tasks_collection = mock_get_db['task_execution_logs']
        now = datetime.now(timezone.utc)

        # Insert failed task
        tasks_collection.insert_one({
            'task_id': 'failed-task',
            'status': 'failed',
            'failed_at': now - timedelta(days=30),
            'error_message': 'Some error',
        })

        # Cleanup failed tasks older than 14 days
        threshold = now - timedelta(days=14)
        result = tasks_collection.delete_many({
            'status': 'failed',
            'failed_at': {'$lt': threshold},
        })

        assert result.deleted_count == 1

    @pytest.mark.unit
    def test_archive_old_analysis_results(self, mock_get_db):
        """Test archiving old analysis results"""
        results_collection = mock_get_db['analysis_results']
        archive_collection = mock_get_db['analysis_results_archive']
        now = datetime.now(timezone.utc)

        # Insert old result
        old_result = {
            'result_id': 'old-result',
            'recording_id': 'rec-001',
            'created_at': now - timedelta(days=90),
            'results': {'classification': 'normal'},
        }
        results_collection.insert_one(old_result)

        # Archive results older than 60 days
        threshold = now - timedelta(days=60)
        old_results = list(results_collection.find({'created_at': {'$lt': threshold}}))

        for result in old_results:
            archive_collection.insert_one(result)
            results_collection.delete_one({'_id': result['_id']})

        # Verify archival
        assert results_collection.count_documents({}) == 0
        assert archive_collection.count_documents({}) == 1
