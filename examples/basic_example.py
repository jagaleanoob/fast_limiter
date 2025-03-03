"""
Example FastAPI application demonstrating rate limiting functionality.
"""

import uvicorn
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
import redis

# Import the rate limiting components
from rate_limiter import (
    rate_limit,
    InMemoryRateLimiter,
    RedisRateLimiter,
    TokenBucketRateLimiter,
    FixedWindowRateLimiter,
)

app = FastAPI(title="Rate Limiter Demo")

# Create rate limiter instances
in_memory_limiter = InMemoryRateLimiter()

# Uncomment to use Redis limiter
# redis_client = redis.Redis(host="localhost", port=6379, db=0)
# redis_limiter = RedisRateLimiter(redis_client)

# Token bucket with in-memory storage
token_bucket_limiter = TokenBucketRateLimiter(in_memory_limiter)

# Fixed window with in-memory storage and jitter
fixed_window_limiter = FixedWindowRateLimiter(in_memory_limiter, jitter_seconds=2)


# Custom identifier function (example: use user agent + IP)
def custom_identifier(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "unknown")
    client_ip = request.client.host
    return f"{client_ip}:{user_agent}"


@app.get("/")
async def root():
    return {"message": "Rate limiter demo. Try the different endpoints."}


# Basic in-memory rate limiter (5 requests per minute)
@app.get("/basic")
@rate_limit(requests_limit=5, window_seconds=60)
async def basic_endpoint(request: Request):
    return {"message": "Basic rate limiting (5 per minute)"}


# Custom identifier based on user-agent + IP (3 requests per minute)
@app.get("/custom-identifier")
@rate_limit(requests_limit=3, window_seconds=60, identifier_func=custom_identifier)
async def custom_id_endpoint(request: Request):
    return {"message": "Custom identifier rate limiting (3 per minute)"}


# Token bucket rate limiter (10 requests per minute)
@app.get("/token-bucket")
@rate_limit(requests_limit=10, window_seconds=60, rate_limiter=token_bucket_limiter)
async def token_bucket_endpoint(request: Request):
    return {"message": "Token bucket rate limiting (10 per minute)"}


# Fixed window rate limiter with jitter (8 requests per minute)
@app.get("/fixed-window")
@rate_limit(requests_limit=8, window_seconds=60, rate_limiter=fixed_window_limiter)
async def fixed_window_endpoint(request: Request):
    return {"message": "Fixed window rate limiting with jitter (8 per minute)"}


# Example of applying rate limiting to a specific dependency
async def rate_limited_dependency(request: Request):
    """This dependency is rate limited to 2 requests per 30 seconds"""
    # Rate limiting is performed here
    return {"dep_data": "This is rate-limited data"}


@app.get("/dependency-example")
async def dependency_example(
    request: Request,
    limited_data=Depends(rate_limit(requests_limit=2, window_seconds=30)(rate_limited_dependency)),
):
    return {
        "message": "Endpoint with rate-limited dependency (2 per 30 seconds)",
        "data": limited_data,
    }


# Error handler for rate limit exceeded
@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc.detail)},
        headers={"Retry-After": exc.headers.get("Retry-After", "60")},
    )


if __name__ == "__main__":
    uvicorn.run("example:app", host="0.0.0.0", port=8000, reload=True)
