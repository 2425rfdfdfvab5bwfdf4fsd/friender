"""System tools — system_monitor."""
from __future__ import annotations
import platform
import time

import psutil


def system_monitor(include_processes: bool = True,
                   top_n_processes: int = 10) -> dict:
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_hours = uptime_seconds / 3600

    result = {
        "platform": platform.system(),
        "platform_version": platform.version()[:80],
        "cpu": {
            "percent": cpu_percent,
            "count": cpu_count,
        },
        "memory": {
            "total_mb": round(mem.total / 1024 / 1024),
            "available_mb": round(mem.available / 1024 / 1024),
            "used_percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            "free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
            "used_percent": disk.percent,
        },
        "uptime_hours": round(uptime_hours, 1),
    }

    if include_processes:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent",
                                          "memory_percent", "status"]):
            try:
                processes.append({
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "cpu_percent": proc.info["cpu_percent"],
                    "memory_percent": round(proc.info["memory_percent"] or 0, 2),
                    "status": proc.info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        processes.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        result["top_processes"] = processes[:top_n_processes]
        result["total_processes"] = len(processes)

    return result
