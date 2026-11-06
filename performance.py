"""
Rate limiting and performance metrics for production optimization.
"""
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict
import threading


class RateLimiter:
    """Bounded process-local sliding window; deploy one worker until using shared limits."""
    def __init__(self, requests_per_minute=60, requests_per_hour=1000, max_keys=10000):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.max_keys = max_keys
        self._requests = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0

    def is_allowed(self, ip):
        import time
        now = time.monotonic()
        with self._lock:
            if now - self._last_cleanup >= 60:
                self._requests = {k: v for k, v in self._requests.items() if v and v[-1] > now - 3600}
                self._last_cleanup = now
            if ip not in self._requests and len(self._requests) >= self.max_keys:
                return False, {"retry_after": 60}
            entries = self._requests.setdefault(ip, [])
            entries[:] = [stamp for stamp in entries if stamp > now - 3600]
            recent = [stamp for stamp in entries if stamp > now - 60]
            if len(recent) >= self.requests_per_minute or len(entries) >= self.requests_per_hour:
                retry = (recent[0] + 60 if len(recent) >= self.requests_per_minute else entries[0] + 3600) - now
                return False, {"retry_after": max(1, int(retry) + 1)}
            entries.append(now)
            return True, {"remaining_minute": self.requests_per_minute - len(recent) - 1,
                          "remaining_hour": self.requests_per_hour - len(entries)}

    def clear(self):
        with self._lock:
            self._requests.clear()

    def get_stats(self, ip=None):
        with self._lock:
            if ip is not None:
                return {"ip": ip, "requests_tracked": len(self._requests.get(ip, []))}
            return {"ips_tracked": len(self._requests), "total_entries": sum(map(len, self._requests.values()))}


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
