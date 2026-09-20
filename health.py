"""
Health check and metrics endpoints for AI Code Mentor backend.

Provides:
- /health: Detailed system health status with component checks
- /metrics: Prometheus-compatible metrics endpoint
- Connection pooling and resource monitoring
"""

import sqlite3
import psutil
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Tuple
from contextlib import contextmanager

# Track startup time for uptime calculation
_START_TIME = time.time()

# Connection pool for database health checks (max 3 concurrent checks)
class SimpleConnectionPool:
    """Lightweight connection pool for health checks only"""
    def __init__(self, db_path: str, max_connections: int = 3):
        self.db_path = db_path
        self.max_connections = max_connections
        self.connections: List[Tuple[sqlite3.Connection, float]] = []
        self.lock_acquired = False

    @contextmanager
    def get_connection(self):
        """Context manager for pooled database connections"""
        start = time.time()
        conn = None

        try:
            if len(self.connections) < self.max_connections:
                conn = sqlite3.connect(self.db_path, timeout=5.0)
            else:
                # Reuse oldest idle connection
                conn, _ = self.connections.pop(0)

            yield conn

        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Database connection failed: {str(e)}")

        finally:
            if conn:
                elapsed = time.time() - start
                if len(self.connections) < self.max_connections:
                    self.connections.append((conn, elapsed))
                else:
                    conn.close()

    def close_all(self):
        """Close all pooled connections"""
        for conn, _ in self.connections:
            try:
                conn.close()
            except Exception:
                pass
        self.connections.clear()


class HealthChecker:
    """Performs comprehensive system health checks"""

    def __init__(self, db_path: str = "code_mentor.db"):
        self.db_path = db_path
        self.pool = SimpleConnectionPool(db_path)
        self.last_metrics_time = time.time()

    def check_database(self) -> Dict[str, Any]:
        """
        Check database connectivity and response time.
        Returns: {'status': 'ok'|'failed', 'response_time_ms': float, 'details': str}
        """
        start = time.time()
        try:
            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                # Quick query to test connectivity
                cursor.execute("SELECT COUNT(*) FROM users")
                cursor.fetchone()
                conn.close()

            response_time = (time.time() - start) * 1000
            return {
                "status": "ok",
                "response_time_ms": round(response_time, 2),
                "details": "Database responding normally"
            }

        except Exception as e:
            response_time = (time.time() - start) * 1000
            return {
                "status": "failed",
                "response_time_ms": round(response_time, 2),
                "details": f"Database error: {str(e)}"
            }

    def check_memory(self) -> Dict[str, Any]:
        """
        Check process memory usage.
        Returns: {'usage_percent': float, 'rss_mb': float, 'vms_mb': float}
        """
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            mem_percent = process.memory_percent()

            return {
                "usage_percent": round(mem_percent, 2),
                "rss_mb": round(mem_info.rss / 1024 / 1024, 2),
                "vms_mb": round(mem_info.vms / 1024 / 1024, 2)
            }
        except Exception as e:
            return {
                "usage_percent": 0,
                "rss_mb": 0,
                "vms_mb": 0,
                "error": str(e)
            }

    def check_cpu(self) -> Dict[str, Any]:
        """
        Check CPU usage (1-second sample).
        Returns: {'percent': float, 'count': int}
        """
        try:
            process = psutil.Process(os.getpid())
            cpu_percent = process.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()

            return {
                "percent": round(cpu_percent, 2),
                "count": cpu_count
            }
        except Exception as e:
            return {
                "percent": 0,
                "count": 0,
                "error": str(e)
            }

    def check_uptime(self) -> Dict[str, Any]:
        """
        Check service uptime since startup.
        Returns: {'uptime_seconds': int, 'uptime_human': str}
        """
        uptime_seconds = int(time.time() - _START_TIME)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        return {
            "uptime_seconds": uptime_seconds,
            "uptime_human": f"{hours}h {minutes}m {seconds}s"
        }

    def check_disk(self) -> Dict[str, Any]:
        """
        Check disk space where database is located.
        Returns: {'total_gb': float, 'used_gb': float, 'free_gb': float, 'percent': float}
        """
        try:
            db_dir = os.path.dirname(os.path.abspath(self.db_path)) or "."
            disk = psutil.disk_usage(db_dir)

            return {
                "total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
                "used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
                "free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
                "percent": disk.percent
            }
        except Exception as e:
            return {
                "total_gb": 0,
                "used_gb": 0,
                "free_gb": 0,
                "percent": 0,
                "error": str(e)
            }

    def get_overall_status(self, checks: Dict[str, Any]) -> str:
        """
        Determine overall health based on component checks.
        Returns: 'healthy' | 'degraded' | 'down'
        """
        db_status = checks.get("database", {}).get("status", "unknown")
        memory = checks.get("memory", {}).get("usage_percent", 0)
        disk = checks.get("disk", {}).get("percent", 0)

        # Down conditions
        if db_status == "failed":
            return "down"

        # Degraded conditions
        if memory > 90 or disk > 95:
            return "degraded"

        return "healthy"

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status.

        Returns:
        {
            "status": "healthy" | "degraded" | "down",
            "timestamp": "ISO format",
            "version": "1.0.0",
            "uptime": {...},
            "checks": {
                "database": {...},
                "memory": {...},
                "cpu": {...},
                "disk": {...}
            }
        }
        """
        checks = {
            "database": self.check_database(),
            "memory": self.check_memory(),
            "cpu": self.check_cpu(),
            "disk": self.check_disk(),
        }

        overall_status = self.get_overall_status(checks)
        uptime = self.check_uptime()

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0.0",
            "uptime": uptime,
            "checks": checks
        }

    def get_prometheus_metrics(self) -> str:
        """
        Get metrics in Prometheus text format.

        Format:
        # HELP metric_name Description
        # TYPE metric_name gauge
        metric_name{label="value"} value
        """
        metrics_lines = [
            "# HELP service_health_status Overall service health (0=down, 1=degraded, 2=healthy)",
            "# TYPE service_health_status gauge",
        ]

        health = self.get_health_status()

        # Convert status to numeric
        status_map = {"down": 0, "degraded": 1, "healthy": 2}
        status_value = status_map.get(health["status"], 0)
        metrics_lines.append(f"service_health_status {status_value}")

        # Uptime
        metrics_lines.extend([
            "# HELP service_uptime_seconds Service uptime in seconds",
            "# TYPE service_uptime_seconds counter",
            f"service_uptime_seconds {health['uptime']['uptime_seconds']}"
        ])

        # Database metrics
        db_check = health["checks"]["database"]
        metrics_lines.extend([
            "# HELP database_response_time_ms Database query response time in milliseconds",
            "# TYPE database_response_time_ms gauge",
            f"database_response_time_ms {db_check.get('response_time_ms', 0)}"
        ])

        db_status_map = {"ok": 1, "failed": 0}
        metrics_lines.extend([
            "# HELP database_status Database connectivity status (0=failed, 1=ok)",
            "# TYPE database_status gauge",
            f"database_status {db_status_map.get(db_check.get('status'), 0)}"
        ])

        # Memory metrics
        mem_check = health["checks"]["memory"]
        metrics_lines.extend([
            "# HELP process_memory_rss_bytes Process resident set size in bytes",
            "# TYPE process_memory_rss_bytes gauge",
            f"process_memory_rss_bytes {int(mem_check.get('rss_mb', 0) * 1024 * 1024)}"
        ])

        metrics_lines.extend([
            "# HELP process_memory_percent Memory usage as percentage",
            "# TYPE process_memory_percent gauge",
            f"process_memory_percent {mem_check.get('usage_percent', 0)}"
        ])

        # CPU metrics
        cpu_check = health["checks"]["cpu"]
        metrics_lines.extend([
            "# HELP process_cpu_percent CPU usage as percentage",
            "# TYPE process_cpu_percent gauge",
            f"process_cpu_percent {cpu_check.get('percent', 0)}"
        ])

        # Disk metrics
        disk_check = health["checks"]["disk"]
        metrics_lines.extend([
            "# HELP disk_usage_percent Disk usage as percentage",
            "# TYPE disk_usage_percent gauge",
            f"disk_usage_percent {disk_check.get('percent', 0)}"
        ])

        metrics_lines.extend([
            "# HELP disk_free_bytes Free disk space in bytes",
            "# TYPE disk_free_bytes gauge",
            f"disk_free_bytes {int(disk_check.get('free_gb', 0) * 1024 * 1024 * 1024)}"
        ])

        return "\n".join(metrics_lines) + "\n"


def get_health_checker(db_path: str = "code_mentor.db") -> HealthChecker:
    """Factory function to get or create health checker instance"""
    if not hasattr(get_health_checker, '_instance'):
        get_health_checker._instance = HealthChecker(db_path)
    return get_health_checker._instance
