import pytest
from mcp_servers._http import CircuitBreaker, CircuitState, structured_error_response

def test_circuit_breaker_stays_closed_on_success():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.allow_request("https://api.example.com") is True
    cb.record_success("https://api.example.com")
    assert cb.allow_request("https://api.example.com") is True

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure("https://api.example.com")
    assert cb.allow_request("https://api.example.com") is False

def test_structured_error_response_includes_required_fields():
    err = structured_error_response(Exception("test"), "noaa", "get_weather")
    assert err["success"] is False
    assert err["server"] == "noaa"
    assert err["tool"] == "get_weather"
    assert "error_category" in err
