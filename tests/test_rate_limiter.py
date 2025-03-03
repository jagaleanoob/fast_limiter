import time
import pytest
from unittest.mock import MagicMock, patch
from fast_limiter import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    TokenBucketRateLimiter,
    FixedWindowRateLimiter,
)


class TestInMemoryRateLimiter:
    def test_first_request_allowed(self):
        limiter = InMemoryRateLimiter()
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        assert limiter.request_records["test_client"][0] == 1  # count
    
    def test_under_limit_allowed(self):
        limiter = InMemoryRateLimiter()
        # First request
        limiter.check_rate_limit("test_client", 5, 60)
        
        # Second request
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        assert limiter.request_records["test_client"][0] == 2  # count

    def test_limit_exceeded_blocked(self):
        limiter = InMemoryRateLimiter()
        # Set up a client that has reached the limit
        current_time = time.time()
        limiter.request_records["test_client"] = (5, current_time)
        
        # Try another request
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is False
        assert retry_after > 0  # Should suggest a wait time
        assert retry_after <= 60

    def test_window_expiry_resets_count(self):
        limiter = InMemoryRateLimiter()
        # Set up a client with an expired window
        current_time = time.time()
        limiter.request_records["test_client"] = (5, current_time - 61)  # 61 seconds ago
        
        # New request after window expiry
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        assert limiter.request_records["test_client"][0] == 1  # count reset

    def test_data_storage(self):
        limiter = InMemoryRateLimiter()
        
        # Test set_data
        limiter.set_data("test_key", "test_value", ttl=60)
        
        # Test get_data
        value = limiter.get_data("test_key")
        assert value == ("test_value", 60)
        
        # Test for non-existent key
        value = limiter.get_data("non_existent_key")
        assert value is None


class TestRedisRateLimiter:
    @pytest.fixture
    def mock_redis(self):
        redis_mock = MagicMock()
        pipe_mock = MagicMock()
        redis_mock.pipeline.return_value = pipe_mock
        pipe_mock.execute.return_value = [None, None]  # Default: no previous records
        return redis_mock, pipe_mock

    def test_first_request_allowed(self, mock_redis):
        redis_mock, pipe_mock = mock_redis
        limiter = RedisRateLimiter(redis_mock)
        
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        # Verify Redis operations
        assert pipe_mock.set.call_count == 2
        assert pipe_mock.execute.call_count == 2

    def test_under_limit_allowed(self, mock_redis):
        redis_mock, pipe_mock = mock_redis
        limiter = RedisRateLimiter(redis_mock)
        
        # Mock existing counter
        pipe_mock.execute.return_value = [b"3", str(time.time()).encode()]
        
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        assert redis_mock.incr.called

    def test_limit_exceeded_blocked(self, mock_redis):
        redis_mock, pipe_mock = mock_redis
        limiter = RedisRateLimiter(redis_mock)
        
        # Mock reaching the limit
        current_time = time.time()
        pipe_mock.execute.return_value = [b"5", str(current_time).encode()]
        
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is False
        assert retry_after > 0
        assert retry_after <= 60

    def test_window_expiry_resets_count(self, mock_redis):
        redis_mock, pipe_mock = mock_redis
        limiter = RedisRateLimiter(redis_mock)
        
        # Mock an expired window
        expired_time = time.time() - 61  # 61 seconds ago
        pipe_mock.execute.return_value = [b"5", str(expired_time).encode()]
        
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        assert pipe_mock.set.call_count == 2
        assert pipe_mock.execute.call_count == 2


class TestTokenBucketRateLimiter:
    def test_first_request_allowed(self):
        storage_mock = MagicMock()
        storage_mock.get_data.return_value = None
        
        limiter = TokenBucketRateLimiter(storage_mock)
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        # Verify bucket initialization
        assert storage_mock.set_data.call_count == 2

    def test_bucket_refill(self):
        storage_mock = MagicMock()
        current_time = time.time()
        old_time = current_time - 30  # 30 seconds ago
        
        # Mock half-empty bucket with last update 30 seconds ago
        storage_mock.get_data.side_effect = lambda key: {
            "bucket:test_client": "2.5",
            "last_update:test_client": str(old_time)
        }.get(key)
        
        limiter = TokenBucketRateLimiter(storage_mock)
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        # Check tokens were refilled and one was consumed
        assert storage_mock.set_data.call_count == 2

    def test_empty_bucket_blocked(self):
        storage_mock = MagicMock()
        current_time = time.time()
        
        # Mock empty bucket
        storage_mock.get_data.side_effect = lambda key: {
            "bucket:test_client": "0.5",
            "last_update:test_client": str(current_time - 1)
        }.get(key)
        
        limiter = TokenBucketRateLimiter(storage_mock)
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is False
        assert retry_after > 0
        # Only last_update should be updated
        assert storage_mock.set_data.call_count == 1


class TestFixedWindowRateLimiter:
    def test_delegates_to_storage(self):
        storage_mock = MagicMock()
        storage_mock.check_rate_limit.return_value = (True, 0)
        
        limiter = FixedWindowRateLimiter(storage_mock)
        is_allowed, retry_after = limiter.check_rate_limit("test_client", 5, 60)
        
        assert is_allowed is True
        assert retry_after == 0
        storage_mock.check_rate_limit.assert_called_once_with("test_client", 5, 60)

    def test_jitter_added(self):
        storage_mock = MagicMock()
        storage_mock.check_rate_limit.return_value = (True, 0)
        
        # Test with jitter
        with patch("random.randint", return_value=3):
            limiter = FixedWindowRateLimiter(storage_mock, jitter_seconds=5)
            limiter.check_rate_limit("test_client", 5, 60)
            
            # Should call with jittered window
            storage_mock.check_rate_limit.assert_called_once_with("test_client", 5, 63)


