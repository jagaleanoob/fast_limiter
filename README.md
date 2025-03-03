# FastAPI Rate Limiter

A flexible, extensible rate limiting library for FastAPI applications.

## Features

- Multiple rate limiting strategies:
  - Basic in-memory rate limiting
  - Redis-backed rate limiting for distributed applications
  - Token bucket algorithm
  - Fixed window with jitter support
- Easy to use decorator syntax
- Customizable identifier extraction
- Proper handling of rate limit headers
- Extensible design for custom rate limiting strategies

## Installation

```bash
pip install fastapi-rate-limiter
```

## Quick Start

```python
from fastapi import FastAPI, Request
from fastapi_rate_limiter import rate_limit, InMemoryRateLimiter

app = FastAPI()

# Basic usage: 5 requests per minute, based on client IP
@app.get("/limited-endpoint")
@rate_limit(requests_limit=5, window_seconds=60)
async def limited_endpoint(request: Request):
    return {"message": "This endpoint is rate limited"}
```

## Rate Limiting Strategies

### In-Memory Rate Limiter

Simple rate limiting using in-memory storage. Good for single-instance applications.

```python
from fastapi_rate_limiter import InMemoryRateLimiter

# Create a rate limiter instance
limiter = InMemoryRateLimiter()

@app.get("/in-memory")
@rate_limit(requests_limit=10, window_seconds=60, rate_limiter=limiter)
async def in_memory_endpoint(request: Request):
    return {"message": "Using in-memory rate limiting"}
```

### Redis Rate Limiter

Distributed rate limiting using Redis. Ideal for multi-instance applications.

```python
import redis
from fastapi_rate_limiter import RedisRateLimiter

# Create Redis client
redis_client = redis.Redis(host="localhost", port=6379, db=0)

# Create Redis rate limiter
redis_limiter = RedisRateLimiter(redis_client)

@app.get("/redis")
@rate_limit(
    requests_limit=20, 
    window_seconds=60, 
    rate_limiter=redis_limiter
)
async def redis_endpoint(request: Request):
    return {"message": "Using Redis-backed rate limiting"}
```

### Token Bucket Rate Limiter

Implements the token bucket algorithm, allowing for bursts of traffic while maintaining a consistent average rate.

```python
from fastapi_rate_limiter import TokenBucketRateLimiter, InMemoryRateLimiter

# Create token bucket with in-memory storage
token_bucket = TokenBucketRateLimiter(
    storage_backend=InMemoryRateLimiter(),
    bucket_capacity=15  # Optional: default is requests_limit
)

@app.get("/token-bucket")
@rate_limit(
    requests_limit=10, 
    window_seconds=60, 
    rate_limiter=token_bucket
)
async def token_bucket_endpoint(request: Request):
    return {"message": "Using token bucket rate limiting"}
```

### Fixed Window Rate Limiter with Jitter

Fixed window rate limiting with jitter to prevent the "thundering herd" problem.

```python
from fastapi_rate_limiter import FixedWindowRateLimiter, InMemoryRateLimiter

# Create fixed window limiter with jitter
fixed_window = FixedWindowRateLimiter(
    storage_backend=InMemoryRateLimiter(),
    jitter_seconds=5  # Add random jitter of 0-5 seconds
)

@app.get("/fixed-window")
@rate_limit(
    requests_limit=15, 
    window_seconds=60, 
    rate_limiter=fixed_window
)
async def fixed_window_endpoint(request: Request):
    return {"message": "Using fixed window rate limiting with jitter"}
```

## Custom Identifier Functions

By default, rate limiting is applied based on the client's IP address and the request path. You can customize this with your own identifier function:

```python
def custom_identifier(request: Request) -> str:
    # Rate limit based on Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # Extract token
        token = auth_header[7:]
        return f"token:{token}"
    # Fallback to IP
    return f"ip:{request.client.host}"

@app.get("/custom-id")
@rate_limit(
    requests_limit=5,
    window_seconds=60,
    identifier_func=custom_identifier
)
async def custom_id_endpoint(request: Request):
    return {"message": "Using custom identifier for rate limiting"}
```

## Handling Rate Limit Errors

Add a custom exception handler to your FastAPI app for better rate limit error responses:

```python
from fastapi.responses import JSONResponse

@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": str(exc.detail),
            "retry_after_seconds": exc.headers.get("Retry-After")
        },
        headers={"Retry-After": exc.headers.get("Retry-After", "60")}
    )
```

## Creating Custom Rate Limiters

You can create your own rate limiting strategy by implementing the `RateLimiter` abstract base class:

```python
from fastapi_rate_limiter import RateLimiter
from typing import Tuple, Optional, Any

class MyCustomRateLimiter(RateLimiter):
    def __init__(self):
        # Initialize your limiter
        pass
    
    def check_rate_limit(
        self, 
        identifier: str, 
        requests_limit: int, 
        window_seconds: int
    ) -> Tuple[bool, int]:
        # Implement your rate limiting logic
        # Return (is_allowed, retry_after_seconds)
        pass
        
    def get_data(self, key: str) -> Any:
        # Implement storage get
        pass
        
    def set_data(self, key: str, value: Any, ttl: Optional[int]) -> None:
        # Implement storage set
        pass
```

## Advanced Usage

### Rate Limiting Dependencies

You can apply rate limiting to FastAPI dependencies:

```python
from fastapi import Depends

async def rate_limited_dependency(request: Request):
    """This dependency is rate limited"""
    return {"data": "Rate limited data"}

@app.get("/with-dependency")
async def dependency_example(
    request: Request,
    limited_data=Depends(
        rate_limit(
            requests_limit=3,
            window_seconds=30
        )(rate_limited_dependency)
    )
):
    return {
        "message": "Using rate-limited dependency",
        "data": limited_data
    }
```

## Testing

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=fastapi_rate_limiter
```

## License

MIT License - see LICENSE file for details.
