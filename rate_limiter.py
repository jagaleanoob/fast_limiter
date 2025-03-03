from abc import ABC, abstractmethod
from fastapi import Request, HTTPException
from typing import Dict, Tuple, Callable, Optional, Any
import time
from functools import wraps

class RateLimiter(ABC):
    @abstractmethod
    def check_rate_limit(self, identifier: str, requests_limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if the rate limit has been exceeded.
        
        Args:
            identifier: The unique identifier for the client
            requests_limit: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
            - is_allowed: True if request is allowed, False if rate limit exceeded
            - retry_after_seconds: Seconds to wait before retry if rate limit exceeded, 0 otherwise
        """
        pass

    def get_data(self, key: str) -> Any:
        """
        Get data from the storage backend.
        
        Args:
            key: The storage key
            
        Returns:
            The stored value or None if not found
        """
        pass

    def set_data(self, key: str, value: Any, ttl: Optional[int]) -> Any:
        """
        Set data in the storage backend.
        
        Args:
            key: The storage key
            value: The value to store
            ttl: Time to live in seconds
        """
        pass

class InMemoryRateLimiter(RateLimiter):
    def __init__(self):
        self.request_records: Dict[str, Tuple[int, float]] = {}
        self.data_store = {}
    
    def check_rate_limit(self, identifier: str, requests_limit: int, window_seconds: int) -> Tuple[bool, int]:
        current_time = time.time()
        
        if identifier in self.request_records:
            requests_count, window_start = self.request_records[identifier]
            
            if current_time - window_start > window_seconds:
                self.request_records[identifier] = (1, current_time)
                return True, 0
            elif requests_count >= requests_limit:
                retry_after = int(window_start + window_seconds - current_time)
                return False, retry_after
            else:
                self.request_records[identifier] = (requests_count + 1, window_start)
                return True, 0
        else:
            self.request_records[identifier] = (1, current_time)
            return True, 0

    def get_data(self, key:str) -> Any:
        """Get data from the in-memory data store"""
        return self.data_store.get(key) 

    def set_data(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set data in the in-memory data store"""
        self.data_store[key] = value, ttl

class RedisRateLimiter(RateLimiter):
    def __init__(self, redis_client, prefix="ratelimit:"):
        """
        Args:
            redis_client: An initialized redis client
            prefix: Prefix for redis keys
        """
        self.redis = redis_client
        self.prefix = prefix
    
    def check_rate_limit(self, identifier: str, requests_limit: int, window_seconds: int) -> Tuple[bool, int]:
        key = f"{self.prefix}{identifier}"
        
        pipe = self.redis.pipeline()
        pipe.get(f"{key}:count")
        pipe.get(f"{key}:start")
        count_bytes, start_bytes = pipe.execute()
        
        current_time = time.time()
        
        if count_bytes and start_bytes:
            count = int(count_bytes)
            start = float(start_bytes)
            
            if current_time - start > window_seconds:
                # Window expired, reset counter
                pipe = self.redis.pipeline()
                pipe.set(f"{key}:count", 1)
                pipe.set(f"{key}:start", current_time)
                pipe.expire(f"{key}:count", window_seconds)
                pipe.expire(f"{key}:start", window_seconds)
                pipe.execute()
                return True, 0
            elif count >= requests_limit:
                retry_after = int(start + window_seconds - current_time)
                return False, retry_after
            else:
                self.redis.incr(f"{key}:count")
                return True, 0

        # First request
        pipe = self.redis.pipeline()
        pipe.set(f"{key}:count", 1)
        pipe.set(f"{key}:start", current_time)
        pipe.expire(f"{key}:count", window_seconds)
        pipe.expire(f"{key}:start", window_seconds)
        pipe.execute()
        return True, 0

    def get_data(self, key:str) -> Any:
        """Get data from Redis"""
        self.redis.get(key)

    def set_data(self, key: str, value: Any, ttl: Optional[int]):
        """Set data in Redis w/optional ttl"""
        self.redis.setex(key, ttl, value) if ttl else self.redis.set(key, value)

class TokenBucketRateLimiter(RateLimiter):
    def __init__(self, storage_backend: Optional[RateLimiter] = None, bucket_capacity: float|None = None):
        """
        Implements token bucket algorithm using another rate limiter for storage
        
        Args:
            storage_backend: A rate limiter implementation to use for storage 
                (defaults to InMemoryRateLimiter)
            bucket_capacity: Max number of tokens the bucket can hold (defaults to requests_limit)
        """
        self.storage = storage_backend or InMemoryRateLimiter()
        self.bucket_capacity = bucket_capacity

    def _get_bucket_data(self, key:str) -> Optional[Any]:
        """Get data from the underlying storage"""
        return self.storage.get_data(key)

    def _set_bucket_data(self, key: str, value: Any, ttl: Optional[int]) -> None:
        """Set data in the underlying storage"""
        self.storage.set_data(key, value, ttl)
    
    def check_rate_limit(self, identifier: str, requests_limit: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if a request is allowed by the token bucket algorithm.
        
        Args:
            identifier: Unique identifier for the client
            requests_limit: Maximum number of requests allowed in the window (also used as bucket capacity if not specified)
            window_seconds: Time window in seconds
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        refill_rate = requests_limit / window_seconds
        bucket_capacity = self.bucket_capacity or requests_limit

        bucket_key = f"bucket:{identifier}"
        last_update_key = f"last_update:{identifier}"

        current_tokens = self._get_bucket_data(bucket_key)
        last_update = self._get_bucket_data(last_update_key)

        current_time = time.time()

        if current_tokens is None or last_update is None:
            self._set_bucket_data(bucket_key, bucket_capacity-1, window_seconds*2)
            self._set_bucket_data(last_update_key, current_time, window_seconds*2)
            return True, 0

        if isinstance(current_tokens, str):
            current_tokens = float(current_tokens)
        if isinstance(last_update, str):
            last_update = float(last_update)

        time_elapsed = current_time - last_update
        tokens_to_add = time_elapsed * refill_rate
        new_token_count = min(current_tokens + tokens_to_add, bucket_capacity)

        if new_token_count >= 1:
            new_token_count -= 1
            self._set_bucket_data(bucket_key, new_token_count, window_seconds*2)
            self._set_bucket_data(last_update_key, current_time, window_seconds*2)
            return True, 0
        
        time_until_next_token = (1 - new_token_count) / refill_rate
        retry_after = int(time_until_next_token + 0.5)
        self._set_bucket_data(last_update_key, current_time, window_seconds*2)
        return False, max(1, retry_after)


class FixedWindowRateLimiter(RateLimiter):
    def __init__(self, storage_backend: RateLimiter, jitter_seconds: int = 0):
        """
        Implements fixed window rate limiting with optional jitter
        
        Args:
            storage_backend: A rate limiter implementation to use for storage
            jitter_seconds: Random time to add to the window to prevent thundering herd
        """
        self.storage = storage_backend
        self.jitter_seconds = jitter_seconds
    
    def check_rate_limit(self, identifier: str, requests_limit: int, window_seconds: int) -> Tuple[bool, int]:
        if self.jitter_seconds > 0:
            import random
            window_seconds += random.randint(0, self.jitter_seconds)
        
        return self.storage.check_rate_limit(identifier, requests_limit, window_seconds)

def rate_limit(
    requests_limit: int, 
    window_seconds: int, 
    identifier_func: Optional[Callable[[Request], str]] = None,
    rate_limiter: RateLimiter|None = None
):
    """
    Rate limiting decorator that can use different backend implementations
    
    Args:
        requests_limit: Maximum number of requests allowed in the window
        window_seconds: Time window in seconds
        identifier_func: Function to extract a unique identifier from the request
        rate_limiter: Rate limiter implementation to use (defaults to InMemoryRateLimiter)
    """
    if identifier_func is None:
        # defaults to client's ip + url path
        identifier_func = lambda request : request.client.host + request.url.path
    
    if rate_limiter is None:
        rate_limiter = InMemoryRateLimiter()
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                for k, v in kwargs.items():
                    if isinstance(v, Request):
                        request = v
                        break
            
            if not request:
                raise ValueError("No FastAPI Request object found in arguments")
            
            identifier = identifier_func(request)
            
            is_allowed, retry_after = rate_limiter.check_rate_limit(identifier, requests_limit, window_seconds)
            
            if not is_allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator
