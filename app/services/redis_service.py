# v3 — Production-stable Redis with automatic in-memory fallback
# app/services/redis_service.py
# ========================================================================

import json
import logging
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from redis import Redis
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError

logger = logging.getLogger(__name__)


class SafeJSONEncoder(json.JSONEncoder):
    """Handles common non-JSON types that appear in ORM responses."""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return super().default(obj)


class _InMemoryStore:
    """Thread-safe in-memory store with TTL support."""

    def __init__(self):
        self._data: dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def _purge_if_expired(self, key: str) -> None:
        entry = self._data.get(key)
        if entry is None:
            return
        _, expires_at = entry
        if expires_at is not None and expires_at < time.monotonic():
            self._data.pop(key, None)

    def get(self, key: str):
        with self._lock:
            self._purge_if_expired(key)
            entry = self._data.get(key)
            return entry[0] if entry else None

    def setex(self, key: str, expiry: int, value: str):
        with self._lock:
            expires_at = time.monotonic() + expiry
            self._data[key] = (value, expires_at)
        return True

    def set(self, key: str, value: str):
        with self._lock:
            self._data[key] = (value, None)
        return True

    def delete(self, *keys: str):
        with self._lock:
            for key in keys:
                self._data.pop(key, None)
        return len(keys)

    def exists(self, *keys: str):
        with self._lock:
            return sum(1 for k in keys if k in self._data)

    def ping(self):
        return True

    def pipeline(self):
        """Return a simple pipeline-like object for rate limiting."""
        return _InMemoryPipeline(self)


class _InMemoryPipeline:
    def __init__(self, store: _InMemoryStore):
        self._store = store
        self._commands: list = []

    def incr(self, key: str):
        self._commands.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int):
        self._commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "incr":
                key = cmd[1]
                with self._store._lock:
                    val = self._store.get(key)
                    val = int(val) + 1 if val else 1
                    self._store.set(key, str(val))
                    results.append(val)
            elif cmd[0] == "expire":
                key, seconds = cmd[1], cmd[2]
                with self._store._lock:
                    entry = self._store._data.get(key)
                    if entry:
                        self._store._data[key] = (entry[0], time.monotonic() + seconds)
                results.append(True)
        return results


class RedisService:
    """
    Production Redis service with automatic in-memory fallback.
    
    If Redis is unreachable, falls back to thread-safe in-memory store
    so the app never crashes on cache unavailability.
    """

    _instance: Optional["RedisService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, connection_string: Optional[str] = None, **kwargs):
        """Singleton pattern — prevents multiple connections per process."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, connection_string: Optional[str] = None):
        # Prevent re-initialization on subsequent calls
        if self._initialized:
            return

        self.connection_string = connection_string
        self.client: Optional[Redis] = None
        self.pool: Optional[ConnectionPool] = None
        self._memory_store: Optional[_InMemoryStore] = None
        self._using_fallback = False

        if connection_string:
            self._initialize_connection(connection_string)
        else:
            logger.warning("RedisService: no connection string provided, using in-memory fallback")
            self._memory_store = _InMemoryStore()
            self._using_fallback = True

        self._initialized = True

    def _initialize_connection(self, connection_string: str):
        """Try Redis; on ANY failure, silently fall back to in-memory."""
        try:
            self.pool = ConnectionPool.from_url(
                connection_string,
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=10,
                retry_on_timeout=True,
                max_connections=10,
            )
            self.client = Redis(connection_pool=self.pool)
            self.client.ping()
            
            from urllib.parse import urlparse
            parsed = urlparse(connection_string)
            logger.info(
                "Redis connected to %s:%s (SSL: %s)",
                parsed.hostname,
                parsed.port or 6379,
                parsed.scheme == "rediss",
            )
            self._using_fallback = False
            
        except Exception as e:
            logger.warning(
                "Redis unavailable (%s: %s) — using in-memory fallback",
                type(e).__name__,
                e,
            )
            self.client = None
            self.pool = None
            self._memory_store = _InMemoryStore()
            self._using_fallback = True

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    def _get_healthy_client(self) -> Redis:
        """Return Redis client or raise if in fallback mode."""
        if self.client is None:
            raise RuntimeError("Redis client not available (in-memory fallback active)")
        try:
            self.client.ping()
            return self.client
        except (RedisConnectionError, ConnectionError, BrokenPipeError) as e:
            logger.warning("Redis connection stale (%s), reconnecting...", e)
            if self.connection_string:
                self._initialize_connection(self.connection_string)
            if self.client:
                return self.client
            raise RuntimeError("Redis reconnection failed")

    def get_client(self) -> Redis:
        """Get raw Redis client. Raises if fallback is active."""
        return self._get_healthy_client()

    def set(
        self,
        key: str,
        value: Any,
        expiry: Optional[int] = None,
        as_json: bool = True,
    ) -> bool:
        try:
            # Serialize dicts/lists
            if as_json and isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, cls=SafeJSONEncoder)

            if self._using_fallback or self.client is None:
                if expiry:
                    return self._memory_store.setex(key, expiry, str(value))
                return self._memory_store.set(key, str(value))

            # Real Redis
            if expiry:
                return bool(self.client.setex(key, expiry, value))
            return bool(self.client.set(key, value))

        except Exception as e:
            logger.error("Redis SET error for key '%s': %s", key, e)
            return False

    def get(
        self,
        key: str,
        as_json: bool = False,
        default: Any = None,
    ) -> Optional[Any]:
        try:
            if self._using_fallback or self.client is None:
                value = self._memory_store.get(key)
            else:
                value = self.client.get(key)

            if value is None:
                return default

            if as_json and isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError as je:
                    logger.warning("JSON decode failed for key '%s': %s", key, je)
                    return value

            return value

        except Exception as e:
            logger.error("Redis GET error for key '%s': %s", key, e)
            return default

    def delete(self, *keys: str) -> int:
        try:
            if self._using_fallback or self.client is None:
                return self._memory_store.delete(*keys)
            return self.client.delete(*keys)
        except Exception as e:
            logger.error("Redis DELETE error: %s", e)
            return 0

    def exists(self, *keys: str) -> int:
        try:
            if self._using_fallback or self.client is None:
                return self._memory_store.exists(*keys)
            return self.client.exists(*keys)
        except Exception as e:
            logger.error("Redis EXISTS error: %s", e)
            return 0

    def increment_rate_limit(
        self,
        key: str,
        window: int = 60,
        limit: int = 50,
    ) -> tuple[int, bool]:
        try:
            if self._using_fallback or self.client is None:
                pipe = self._memory_store.pipeline()
                pipe.incr(key)
                pipe.expire(key, window)
                results = pipe.execute()
                current_count = results[0]
                is_allowed = current_count <= limit
                return current_count, is_allowed

            # Real Redis
            pipe = self.client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            results = pipe.execute()
            current_count = results[0]
            is_allowed = current_count <= limit
            return current_count, is_allowed

        except Exception as e:
            logger.error("Redis rate limit error for key '%s': %s", key, e)
            return 0, True  # Allow on error (fail-open)

    def ping(self) -> bool:
        try:
            if self._using_fallback or self.client is None:
                return self._memory_store.ping()
            return bool(self.client.ping())
        except Exception as e:
            logger.error("Redis PING failed: %s", e)
            return False

    def close(self):
        try:
            if self.pool:
                self.pool.disconnect()
                logger.info("Redis connection pool closed")
        except Exception as e:
            logger.error("Error closing Redis pool: %s", e)


# =====================================================================
# MODULE-LEVEL INSTANCE — cached for dependency injection
# =====================================================================

_redis_service_instance: Optional[RedisService] = None


def get_redis_service_instance(connection_string: Optional[str] = None) -> RedisService:
    """
    Get or create the singleton RedisService instance.
    Call this ONCE at startup, then reuse.
    """
    global _redis_service_instance
    if _redis_service_instance is None:
        _redis_service_instance = RedisService(connection_string)
    return _redis_service_instance


def reset_redis_service():
    """Reset singleton (useful for testing)."""
    global _redis_service_instance
    _redis_service_instance = None

