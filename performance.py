"""
Rate limiting and performance metrics for production optimization.
"""
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import threading


class RateLimiter:
    """Token bucket rate limiter with per-IP tracking."""

    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute per IP
            requests_per_hour: Max requests per hour per IP
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._locks: Dict[str, threading.Lock] = {}
        self._requests: Dict[str, list] = defaultdict(list)
        self._cleanup_thread = None
        self._running = False

    def _get_lock(self, ip: str) -> threading.Lock:
        """Get or create lock for IP."""
        if ip not in self._locks:
            self._locks[ip] = threading.Lock()
        return self._locks[ip]

    def is_allowed(self, ip: str) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request from IP is allowed.

        Returns:
            Tuple of (allowed: bool, info: dict with retry_after and limits)
        """
        now = datetime.now()
        lock = self._get_lock(ip)

        with lock:
            # Clean old entries
            minute_ago = now - timedelta(minutes=1)
            hour_ago = now - timedelta(hours=1)

            requests = self._requests[ip]
            requests[:] = [r for r in requests if r > hour_ago]

            # Count recent requests
            recent_minute = sum(1 for r in requests if r > minute_ago)
            recent_hour = len(requests)

            # Check limits
            minute_ok = recent_minute < self.requests_per_minute
            hour_ok = recent_hour < self.requests_per_hour

            if minute_ok and hour_ok:
                self._requests[ip].append(now)
                return True, {
                    "remaining_minute": self.requests_per_minute - recent_minute - 1,
                    "remaining_hour": self.requests_per_hour - recent_hour - 1,
                    "limit_minute": self.requests_per_minute,
                    "limit_hour": self.requests_per_hour,
                }

            # Calculate retry-after
            if not minute_ok:
                oldest_minute = min(r for r in requests if r > minute_ago)
                retry_after = (oldest_minute - minute_ago).total_seconds() + 1
            else:
                oldest_hour = min(requests)
                retry_after = (oldest_hour - hour_ago).total_seconds() + 1

            return False, {
                "retry_after": int(retry_after),
                "remaining_minute": 0 if not minute_ok else recent_minute,
                "remaining_hour": 0 if not hour_ok else recent_hour,
                "limit_minute": self.requests_per_minute,
                "limit_hour": self.requests_per_hour,
            }

    def get_stats(self, ip: Optional[str] = None) -> Dict:
        """Get rate limiter statistics."""
        if ip:
            lock = self._get_lock(ip)
            with lock:
                requests = self._requests.get(ip, [])
                now = datetime.now()
                minute_ago = now - timedelta(minutes=1)
                recent = sum(1 for r in requests if r > minute_ago)
                return {
                    "ip": ip,
                    "requests_tracked": len(requests),
                    "requests_last_minute": recent,
                }
        else:
            return {
                "ips_tracked": len(self._requests),
                "total_entries": sum(len(r) for r in self._requests.values()),
            }


class PerformanceMetrics:
    """Track performance metrics for endpoints."""

    def __init__(self):
        self._metrics: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()

    def record(
        self,
        endpoint: str,
        method: str,
        response_time_ms: float,
        status_code: int,
        user_id: Optional[str] = None,
    ) -> None:
        """Record an endpoint metric."""
        with self._lock:
            self._metrics[f"{method}:{endpoint}"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "response_time_ms": response_time_ms,
                    "status_code": status_code,
                    "user_id": user_id,
                }
            )

    def get_endpoint_stats(self, endpoint: str, method: str = "GET") -> Dict:
        """Get statistics for an endpoint."""
        key = f"{method}:{endpoint}"

        with self._lock:
            metrics = self._metrics.get(key, [])

        if not metrics:
            return {
                "endpoint": endpoint,
                "method": method,
                "total_requests": 0,
                "error_rate_percent": 0,
            }

        response_times = [m["response_time_ms"] for m in metrics]
        errors = sum(1 for m in metrics if m["status_code"] >= 400)

        return {
            "endpoint": endpoint,
            "method": method,
            "total_requests": len(metrics),
            "avg_response_time_ms": round(sum(response_times) / len(response_times), 2),
            "min_response_time_ms": min(response_times),
            "max_response_time_ms": max(response_times),
            "p95_response_time_ms": round(sorted(response_times)[int(len(response_times) * 0.95)], 2) if len(response_times) > 0 else 0,
            "error_rate_percent": round(errors / len(metrics) * 100, 2),
            "recent_errors": sum(1 for m in metrics[-100:] if m["status_code"] >= 400),
        }

    def get_all_stats(self) -> Dict:
        """Get statistics for all endpoints."""
        with self._lock:
            endpoints = list(self._metrics.keys())

        return {
            "endpoints_tracked": len(endpoints),
            "total_requests": sum(
                len(self._metrics[ep]) for ep in endpoints
            ),
            "endpoints": [
                {
                    "key": ep,
                    **self.get_endpoint_stats(ep.split(":")[1], ep.split(":")[0]),
                }
                for ep in sorted(endpoints)
            ],
        }

    def cleanup_old_metrics(self, hours: int = 24) -> int:
        """Remove metrics older than specified hours. Returns count removed."""
        cutoff = datetime.fromisoformat(
            (datetime.now() - timedelta(hours=hours)).isoformat()
        )

        with self._lock:
            removed = 0
            for endpoint_key in self._metrics:
                old_count = len(self._metrics[endpoint_key])
                self._metrics[endpoint_key] = [
                    m for m in self._metrics[endpoint_key]
                    if datetime.fromisoformat(m["timestamp"]) > cutoff
                ]
                removed += old_count - len(self._metrics[endpoint_key])

        return removed


# Global instances
_rate_limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)
_metrics = PerformanceMetrics()


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    return _rate_limiter


def get_metrics() -> PerformanceMetrics:
    """Get the global metrics instance."""
    return _metrics
