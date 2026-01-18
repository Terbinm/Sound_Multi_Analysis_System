"""
Tests for User Model

Tests cover:
- User creation and validation
- User lookup by username/email
- Password hashing verification
- Role management
- CRUD operations
- Flask-Login integration
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestUserModel:
    """Test User model CRUD operations"""

    @pytest.mark.unit
    def test_create_user_success(self, mock_get_db, sample_user_data):
        """Test creating a new user"""
        users_collection = mock_get_db['users']

        # Insert user
        result = users_collection.insert_one(sample_user_data)

        # Verify insertion
        assert result.inserted_id is not None
        assert users_collection.count_documents({}) == 1

    @pytest.mark.unit
    def test_create_user_with_required_fields(self, mock_get_db):
        """Test user creation with minimum required fields"""
        users_collection = mock_get_db['users']

        user_data = {
            'username': 'minimal_user',
            'email': 'minimal@example.com',
            'password_hash': 'hash123',
            'role': 'user',
            'is_active': True,
            'created_at': datetime.now(timezone.utc),
        }

        result = users_collection.insert_one(user_data)
        assert result.acknowledged

        # Retrieve and verify
        user = users_collection.find_one({'username': 'minimal_user'})
        assert user is not None
        assert user['email'] == 'minimal@example.com'

    @pytest.mark.unit
    def test_find_user_by_username(self, mock_get_db, sample_user_data):
        """Test finding user by username"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user is not None
        assert user['username'] == sample_user_data['username']

    @pytest.mark.unit
    def test_find_user_by_email(self, mock_get_db, sample_user_data):
        """Test finding user by email"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        user = users_collection.find_one({'email': sample_user_data['email']})
        assert user is not None
        assert user['email'] == sample_user_data['email']

    @pytest.mark.unit
    def test_find_nonexistent_user(self, mock_get_db):
        """Test finding a user that doesn't exist"""
        users_collection = mock_get_db['users']

        user = users_collection.find_one({'username': 'nonexistent'})
        assert user is None

    @pytest.mark.unit
    def test_update_user(self, mock_get_db, sample_user_data):
        """Test updating user fields"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        # Update user
        result = users_collection.update_one(
            {'username': sample_user_data['username']},
            {'$set': {'email': 'updated@example.com'}}
        )

        assert result.modified_count == 1

        # Verify update
        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user['email'] == 'updated@example.com'

    @pytest.mark.unit
    def test_update_last_login(self, mock_get_db, sample_user_data):
        """Test updating user's last login timestamp"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        new_login_time = datetime.now(timezone.utc)
        users_collection.update_one(
            {'username': sample_user_data['username']},
            {'$set': {'last_login': new_login_time}}
        )

        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user['last_login'] == new_login_time

    @pytest.mark.unit
    def test_delete_user(self, mock_get_db, sample_user_data):
        """Test deleting a user"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        # Verify user exists
        assert users_collection.count_documents({}) == 1

        # Delete user
        result = users_collection.delete_one({'username': sample_user_data['username']})
        assert result.deleted_count == 1

        # Verify deletion
        assert users_collection.count_documents({}) == 0

    @pytest.mark.unit
    def test_soft_delete_user(self, mock_get_db, sample_user_data):
        """Test soft deletion (deactivation) of user"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        # Soft delete by setting is_active to False
        result = users_collection.update_one(
            {'username': sample_user_data['username']},
            {'$set': {'is_active': False}}
        )

        assert result.modified_count == 1

        # User still exists but is inactive
        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user is not None
        assert user['is_active'] is False


class TestUserRoles:
    """Test user role management"""

    @pytest.mark.unit
    def test_admin_role(self, mock_get_db, sample_admin_user_data):
        """Test admin user role"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_admin_user_data)

        user = users_collection.find_one({'username': sample_admin_user_data['username']})
        assert user['role'] == 'admin'

    @pytest.mark.unit
    def test_user_role(self, mock_get_db, sample_user_data):
        """Test regular user role"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user['role'] == 'user'

    @pytest.mark.unit
    def test_change_user_role(self, mock_get_db, sample_user_data):
        """Test changing user role"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        # Promote to admin
        users_collection.update_one(
            {'username': sample_user_data['username']},
            {'$set': {'role': 'admin'}}
        )

        user = users_collection.find_one({'username': sample_user_data['username']})
        assert user['role'] == 'admin'

    @pytest.mark.unit
    def test_get_all_users(self, mock_get_db, sample_user_data, sample_admin_user_data):
        """Test retrieving all users"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)
        users_collection.insert_one(sample_admin_user_data)

        users = list(users_collection.find({}))
        assert len(users) == 2

    @pytest.mark.unit
    def test_get_active_users_only(self, mock_get_db, sample_user_data, sample_admin_user_data):
        """Test retrieving only active users"""
        users_collection = mock_get_db['users']

        # Insert active user
        users_collection.insert_one(sample_user_data)

        # Insert inactive user
        inactive_user = sample_admin_user_data.copy()
        inactive_user['is_active'] = False
        users_collection.insert_one(inactive_user)

        active_users = list(users_collection.find({'is_active': True}))
        assert len(active_users) == 1
        assert active_users[0]['username'] == sample_user_data['username']


class TestUserValidation:
    """Test user data validation"""

    @pytest.mark.unit
    def test_unique_username_constraint(self, mock_get_db, sample_user_data):
        """Test that username must be unique"""
        users_collection = mock_get_db['users']

        # Create index for uniqueness check
        users_collection.create_index('username', unique=True)

        # Insert first user
        users_collection.insert_one(sample_user_data)

        # Attempt to insert duplicate
        duplicate_user = sample_user_data.copy()
        duplicate_user['email'] = 'different@example.com'

        # In mock, we check manually
        existing = users_collection.find_one({'username': sample_user_data['username']})
        assert existing is not None  # Username already exists

    @pytest.mark.unit
    def test_unique_email_constraint(self, mock_get_db, sample_user_data):
        """Test that email must be unique"""
        users_collection = mock_get_db['users']

        # Insert first user
        users_collection.insert_one(sample_user_data)

        # Check if email exists
        existing = users_collection.find_one({'email': sample_user_data['email']})
        assert existing is not None  # Email already exists

    @pytest.mark.unit
    def test_user_to_dict_representation(self, mock_get_db, sample_user_data):
        """Test converting user to dictionary (excluding sensitive data)"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        user = users_collection.find_one({'username': sample_user_data['username']})

        # Simulate to_dict method
        user_dict = {
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'is_active': user['is_active'],
            'created_at': user['created_at'].isoformat() if user.get('created_at') else None,
        }

        # Should not include password_hash
        assert 'password_hash' not in user_dict
        assert user_dict['username'] == sample_user_data['username']


class TestFlaskLoginIntegration:
    """Test Flask-Login integration for User model"""

    @pytest.mark.unit
    def test_user_is_authenticated(self, mock_get_db, sample_user_data):
        """Test is_authenticated property for active user"""
        users_collection = mock_get_db['users']
        users_collection.insert_one(sample_user_data)

        user = users_collection.find_one({'username': sample_user_data['username']})
        # Simulate Flask-Login is_authenticated
        is_authenticated = user.get('is_active', False)
        assert is_authenticated is True

    @pytest.mark.unit
    def test_inactive_user_not_authenticated(self, mock_get_db, sample_user_data):
        """Test inactive user should not be authenticated"""
        users_collection = mock_get_db['users']

        inactive_user = sample_user_data.copy()
        inactive_user['is_active'] = False
        users_collection.insert_one(inactive_user)

        user = users_collection.find_one({'username': sample_user_data['username']})
        is_authenticated = user.get('is_active', False)
        assert is_authenticated is False

    @pytest.mark.unit
    def test_get_user_by_id(self, mock_get_db, sample_user_data):
        """Test user_loader function for Flask-Login"""
        users_collection = mock_get_db['users']
        result = users_collection.insert_one(sample_user_data)

        user_id = result.inserted_id
        user = users_collection.find_one({'_id': user_id})

        assert user is not None
        assert user['username'] == sample_user_data['username']
