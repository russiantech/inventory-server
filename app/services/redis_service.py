
# v2
# app/services/redis_service.py
# ========================================================================

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any
from urllib.parse import urlparse
from uuid import UUID

from redis import Redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

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
        # Fallback for SQLAlchemy instances or other objects
        if hasattr(obj, "__dict__"):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return super().default(obj)


class RedisService:
    """
    Production Redis service with Upstash-specific optimizations.
    """

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string
        self.client: Optional[Redis] = None
        self.pool: Optional[ConnectionPool] = None
        
        if connection_string:
            self._initialize_connection(connection_string)

    def _initialize_connection(self, connection_string: str):
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
            
            parsed = urlparse(connection_string)
            logger.info(
                "Redis connected to %s:%s (SSL: %s)",
                parsed.hostname,
                parsed.port,
                parsed.scheme == "rediss",
            )
        except Exception as e:
            logger.error("Redis init failed: %s", e)
            raise

    def _get_healthy_client(self) -> Redis:
        if not self.client:
            raise RuntimeError("Redis client not initialized")
        try:
            self.client.ping()
            return self.client
        except (RedisConnectionError, ConnectionError, BrokenPipeError) as e:
            logger.warning("Redis connection stale (%s), reconnecting...", e)
            try:
                self.client = Redis(connection_pool=self.pool)
                self.client.ping()
                logger.info("Redis reconnected successfully")
                return self.client
            except Exception as reconnect_err:
                logger.error("Redis reconnection failed: %s", reconnect_err)
                raise

    def get_client(self) -> Redis:
        """Get raw Redis client (backward compatibility for SCAN, etc.)"""
        return self._get_healthy_client()

    def set(
        self,
        key: str,
        value: Any,
        expiry: Optional[int] = None,
        as_json: bool = True,
    ) -> bool:
        try:
            client = self._get_healthy_client()

            # Serialize dicts/lists safely; pass primitives through untouched
            if as_json and isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, cls=SafeJSONEncoder)

            if expiry:
                return bool(client.setex(key, expiry, value))
            return bool(client.set(key, value))

        except RedisError as e:
            logger.error("Redis SET error for key '%s': %s", key, e)
            return False

    def get(
        self,
        key: str,
        as_json: bool = False,
        default: Any = None,
    ) -> Optional[Any]:
        try:
            client = self._get_healthy_client()
            value = client.get(key)

            if value is None:
                return default

            if as_json:
                try:
                    return json.loads(value)
                except json.JSONDecodeError as je:
                    logger.warning("JSON decode failed for key '%s': %s", key, je)
                    return value

            return value

        except RedisError as e:
            logger.error("Redis GET error for key '%s': %s", key, e)
            return default

    def delete(self, *keys: str) -> int:
        try:
            client = self._get_healthy_client()
            return client.delete(*keys)
        except RedisError as e:
            logger.error("Redis DELETE error: %s", e)
            return 0

    def exists(self, *keys: str) -> int:
        try:
            client = self._get_healthy_client()
            return client.exists(*keys)
        except RedisError as e:
            logger.error("Redis EXISTS error: %s", e)
            return 0

    def increment_rate_limit(
        self,
        key: str,
        window: int = 60,
        limit: int = 50,
    ) -> tuple[int, bool]:
        try:
            client = self._get_healthy_client()
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            results = pipe.execute()
            current_count = results[0]
            is_allowed = current_count <= limit
            return current_count, is_allowed
        except RedisError as e:
            logger.error("Redis rate limit error for key '%s': %s", key, e)
            return 0, True

    def ping(self) -> bool:
        try:
            client = self._get_healthy_client()
            return bool(client.ping())
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



# # v2
# # app/services/redis_service.py
# """
# Redis-backed key/value store with an automatic in-memory fallback.

# If Redis is unreachable (connection refused, timeout, etc.) the service
# transparently falls back to a process-local in-memory dict so signup,
# email-verification, and password-reset flows keep working instead of
# raising 503 "Service temporarily unavailable".

# NOTE: the in-memory fallback is per-process and non-persistent — fine for
# dev/single-instance deployments, not a substitute for real Redis in
# multi-worker/production setups.
# """

# import json
# import logging
# import threading
# import time
# from typing import Any, Optional

# logger = logging.getLogger(__name__)

# try:
#     import redis as redis_lib
# except ImportError:  # pragma: no cover
#     redis_lib = None


# class _InMemoryStore:
#     """Thread-safe in-memory store with TTL support, mimicking the subset
#     of the redis-py API used by RedisService."""

#     def __init__(self):
#         self._data: dict[str, tuple[Any, Optional[float]]] = {}
#         self._lock = threading.Lock()

#     def _purge_if_expired(self, key: str) -> None:
#         entry = self._data.get(key)
#         if entry is None:
#             return
#         _, expires_at = entry
#         if expires_at is not None and expires_at < time.monotonic():
#             self._data.pop(key, None)

#     def get(self, key: str):
#         with self._lock:
#             self._purge_if_expired(key)
#             entry = self._data.get(key)
#             return entry[0] if entry else None

#     def set(self, key: str, value: str, ex: Optional[int] = None):
#         with self._lock:
#             expires_at = time.monotonic() + ex if ex else None
#             self._data[key] = (value, expires_at)
#         return True

#     def delete(self, key: str):
#         with self._lock:
#             self._data.pop(key, None)
#         return True

#     def ping(self):
#         return True


# class RedisService:
#     """Wraps a real Redis client when available, otherwise an in-memory
#     store. The public get/set/delete API is identical either way, so
#     callers (auth.py etc.) don't need to know which backend is active."""

#     def __init__(self, url: str = "redis://localhost:6379/0"):
#         self._memory_store: Optional[_InMemoryStore] = None
#         self._client = None

#         if redis_lib is not None:
#             try:
#                 client = redis_lib.from_url(
#                     url, decode_responses=True, socket_connect_timeout=1
#                 )
#                 client.ping()
#                 self._client = client
#                 logger.info("RedisService: connected to Redis at %s", url)
#             except Exception as exc:  # noqa: BLE001
#                 logger.warning(
#                     "RedisService: Redis unavailable (%s) — using in-memory fallback",
#                     exc,
#                 )
#         else:
#             logger.warning(
#                 "RedisService: 'redis' package not installed — using in-memory fallback"
#             )

#         if self._client is None:
#             self._memory_store = _InMemoryStore()

#     @property
#     def using_fallback(self) -> bool:
#         return self._client is None

#     def get(self, key: str, as_json: bool = False) -> Any:
#         try:
#             if self._client is not None:
#                 raw = self._client.get(key)
#             else:
#                 raw = self._memory_store.get(key)
#         except Exception as exc:  # noqa: BLE001
#             logger.error("RedisService.get error for key=%s: %s", key, exc)
#             return None

#         if raw is None:
#             return None
#         if as_json:
#             try:
#                 return json.loads(raw)
#             except (TypeError, ValueError):
#                 return None
#         return raw

#     def set(self, key: str, value: Any, expiry: Optional[int] = None) -> bool:
#         if not isinstance(value, str):
#             value = json.dumps(value)
#         try:
#             if self._client is not None:
#                 if expiry:
#                     return bool(self._client.set(key, value, ex=expiry))
#                 return bool(self._client.set(key, value))
#             return self._memory_store.set(key, value, ex=expiry)
#         except Exception as exc:  # noqa: BLE001
#             logger.error("RedisService.set error for key=%s: %s", key, exc)
#             return False

#     def delete(self, key: str) -> bool:
#         try:
#             if self._client is not None:
#                 self._client.delete(key)
#             else:
#                 self._memory_store.delete(key)
#             return True
#         except Exception as exc:  # noqa: BLE001
#             logger.error("RedisService.delete error for key=%s: %s", key, exc)
#             return False
