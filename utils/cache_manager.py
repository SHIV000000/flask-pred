# utils/cache_manager.py

from functools import lru_cache
from datetime import datetime, timedelta
import threading
import time

class CacheManager:
    def __init__(self):
        self._cache = {}
        self._cache_times = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key in self._cache:
                # Check if cache is still valid
                if datetime.now() < self._cache_times[key]:
                    return self._cache[key]
                else:
                    # Remove expired cache
                    del self._cache[key]
                    del self._cache_times[key]
        return None

    def set(self, key, value, expires_in_minutes=15):
        with self._lock:
            self._cache[key] = value
            self._cache_times[key] = datetime.now() + timedelta(minutes=expires_in_minutes)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._cache_times.clear()

    def clear_old(self):
        """Clear expired cache entries"""
        with self._lock:
            current_time = datetime.now()
            expired_keys = [
                key for key, expire_time in self._cache_times.items()
                if current_time >= expire_time
            ]
            for key in expired_keys:
                del self._cache[key]
                del self._cache_times[key]

cache_manager = CacheManager()


