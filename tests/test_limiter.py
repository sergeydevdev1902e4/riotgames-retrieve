import time
import pytest
from riotgames_retrieve.limiter import RateLimiter, parse_rate_limits


def test_parse_rate_limits():
    header_limits = "20:1,100:120"
    header_counts = "5:1,35:120"
    windows = parse_rate_limits(header_limits, header_counts)
    
    assert len(windows) == 2
    assert windows[0].limit == 20
    assert windows[0].duration == 1.0
    assert windows[0].count == 5
    
    assert windows[1].limit == 100
    assert windows[1].duration == 120.0
    assert windows[1].count == 35


def test_parse_empty_headers():
    assert parse_rate_limits(None, None) == []
    assert parse_rate_limits("", "") == []


def test_limiter_can_proceed_under_limit():
    limiter = RateLimiter()
    limiter.update_from_headers(
        "20:1,100:120",
        "1:1,1:120",
    )
    assert limiter.get_delay() == 0.0


def test_limiter_calculates_sleep_when_saturated():
    limiter = RateLimiter(safety_margin=0.05)
    # simulate hitting 20/20 in 1s window
    limiter.update_from_headers(
        "20:1,100:120",
        "20:1,20:120",
    )
    delay = limiter.get_delay()
    assert delay > 0.0
    assert delay <= 1.1


def test_retry_after_override():
    limiter = RateLimiter()
    limiter.record_429(retry_after=3.5)
    assert limiter.get_delay() >= 3.4


def test_method_limit_takes_precedence():
    limiter = RateLimiter()
    # app is fine, but match-v5 method limit is maxed out
    limiter.update_from_headers(
        app_limits="20:1,100:120",
        app_counts="5:1,20:120",
        method_limits="50:10",
        method_counts="50:10",
        method="match-v5.getMatch",
    )
    delay = limiter.get_delay(method="match-v5.getMatch")
    assert delay > 0.0
    # other method shouldn't be blocked by getMatch limit
    assert limiter.get_delay(method="summoner-v4.getByPuuid") == 0.0


def test_burst_reserve_prevents_lockout():
    # if burst threshold is 0.9, 18/20 requests should already ask for a tiny pause
    limiter = RateLimiter(burst_ratio=0.9)
    limiter.update_from_headers("20:1", "18:1")
    # print(f"calculated delay: {limiter.get_delay()}")
    assert limiter.get_delay() > 0
