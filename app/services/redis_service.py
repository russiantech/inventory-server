
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

