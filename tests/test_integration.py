import pytest
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from fast_limiter import (
    rate_limit,
    InMemoryRateLimiter
)


@pytest.fixture(autouse=True)
def mock_isinstance():
    original_isinstance = isinstance
    
    def patched_isinstance(obj, classinfo):
        if classinfo is Request and isinstance(obj, MagicMock):
            return True
        return original_isinstance(obj, classinfo)
    
    with patch('fast_limiter.rate_limiter.isinstance', side_effect=patched_isinstance):
        yield

@pytest.fixture
def mock_request():
    request_mock = MagicMock()
    
    client_mock = MagicMock()
    client_mock.host = "127.0.0.1"
    request_mock.client = client_mock
    
    url_mock = MagicMock()
    url_mock.path = "/test"
    request_mock.url = url_mock
    
    return request_mock


class TestRateLimitDecorator:
    @pytest.mark.asyncio
    async def test_decorator_allows_request(self, mock_request):
        limiter = MagicMock()
        limiter.check_rate_limit.return_value = (True, 0)
        
        @rate_limit(5, 60, rate_limiter=limiter)
        async def test_endpoint(request):
            return {"message": "success"}
        
        result = await test_endpoint(mock_request)
        assert result == {"message": "success"}
        limiter.check_rate_limit.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_blocks_request(self, mock_request):
        limiter = MagicMock()
        limiter.check_rate_limit.return_value = (False, 30)
        
        @rate_limit(5, 60, rate_limiter=limiter)
        async def test_endpoint(request):
            return {"message": "success"}
        
        with pytest.raises(HTTPException) as excinfo:
            await test_endpoint(mock_request)
        
        assert excinfo.value.status_code == 429
        assert "Rate limit exceeded" in excinfo.value.detail
        assert excinfo.value.headers["Retry-After"] == "30"

    @pytest.mark.asyncio
    async def test_custom_identifier(self, mock_request):
        limiter = MagicMock()
        limiter.check_rate_limit.return_value = (True, 0)
        
        def custom_id(request):
            return "custom-id"
        
        @rate_limit(5, 60, identifier_func=custom_id, rate_limiter=limiter)
        async def test_endpoint(request):
            return {"message": "success"}
        
        await test_endpoint(mock_request)
        limiter.check_rate_limit.assert_called_once_with("custom-id", 5, 60)

    @pytest.mark.asyncio
    async def test_request_in_kwargs(self, mock_request):
        limiter = MagicMock()
        limiter.check_rate_limit.return_value = (True, 0)
        
        @rate_limit(5, 60, rate_limiter=limiter)
        async def test_endpoint(other_arg, request=None):
            return {"message": "success"}
        
        await test_endpoint("test", request=mock_request)
        limiter.check_rate_limit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_request_raises_error(self):
        @rate_limit(5, 60)
        async def test_endpoint(something_else):
            return {"message": "success"}
        
        with pytest.raises(ValueError) as excinfo:
            await test_endpoint("no request here")
        
        assert "No FastAPI Request object found" in str(excinfo.value)


# ----------------------
# Test with real FastAPI application
# ----------------------


def test_fastapi_integration():
    app = FastAPI()
    limiter = InMemoryRateLimiter()
    
    @app.get("/test-endpoint")
    @rate_limit(2, 60, rate_limiter=limiter)
    async def test_endpoint(request: Request):
        return {"message": "success"}
    
    client = TestClient(app)
    
    # First request should succeed
    response1 = client.get("/test-endpoint")
    assert response1.status_code == 200
    
    # Second request should succeed
    response2 = client.get("/test-endpoint")
    assert response2.status_code == 200
    
    # Third request should be rate limited
    response3 = client.get("/test-endpoint")
    assert response3.status_code == 429
    assert "Rate limit exceeded" in response3.json()["detail"]
    assert "Retry-After" in response3.headers
