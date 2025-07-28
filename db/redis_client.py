"""
AURELIUS Redis Client Module
Handles async Redis connections with fallback to local file storage.
"""

import json
import asyncio
from typing import Any, Optional, Dict, List, Union
from pathlib import Path
import redis.asyncio as redis  # <--- ESTA ES LA BUENA
import aiofiles
from datetime import datetime, timedelta
import pickle
import os

from ..logging_config import get_logger, log_data_operation

logger = get_logger("REDIS")

def key_to_filename(key: str) -> str:
    return key.replace(':', '_')


class AureliusDataClient:
    """
    Async data client with Redis primary and local file fallback.
    Ensures no data loss for sales, leads, and interactions.
    """
    
    def __init__(self, redis_url: Optional[str] = None, fallback_path: str = "data/"):
        self.redis_url = redis_url
        self.fallback_path = Path(fallback_path)
        self.redis_client: Optional[redis.Redis] = None
        self.use_redis = False
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        
        # Ensure fallback directory exists
        self.fallback_path.mkdir(parents=True, exist_ok=True)
    
    async def connect(self) -> bool:
        """
        Attempt to connect to Redis. Falls back to local storage if connection fails.
        Returns True if Redis connection successful, False if using fallback.
        """
        if not self.redis_url:
            logger.warning("⚠️  No Redis URL provided, using local file storage")
            return False
        
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
 
            
            # Test connection
            await self.redis_client.ping()
            self.use_redis = True
            self.connection_attempts = 0
            logger.info("✅ Redis connection established successfully")
            return True
            
        except Exception as e:
            self.connection_attempts += 1
            logger.error(f"❌ Redis connection failed (attempt {self.connection_attempts}/{self.max_connection_attempts}): {e}")
            
            if self.connection_attempts >= self.max_connection_attempts:
                logger.warning("⚠️  Max Redis connection attempts reached, falling back to local storage")
                self.use_redis = False
                return False
            
            # Retry after delay
            await asyncio.sleep(2 ** self.connection_attempts)
            return await self.connect()
    
    async def disconnect(self):
        """Close Redis connection if active."""
        if self.redis_client:
            try:
                await self.redis_client.close()
                logger.info("✅ Redis connection closed")
            except Exception as e:
                logger.error(f"❌ Error closing Redis connection: {e}")
    
    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        Set a key-value pair with optional expiration.
        Returns True if successful.
        """
        try:
            if self.use_redis and self.redis_client:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                
                await self.redis_client.set(key, value, ex=expire)
                log_data_operation("SET", "redis", success=True)
                return True
            else:
                return await self._set_local(key, value, expire)
                
        except Exception as e:
            logger.error(f"❌ Failed to set key '{key}': {e}")
            log_data_operation("SET", "redis", success=False, error=str(e))
            
            # Fallback to local storage
            if self.use_redis:
                logger.warning("⚠️  Falling back to local storage for this operation")
                return await self._set_local(key, value, expire)
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value by key.
        Returns None if key doesn't exist.
        """
        try:
            if self.use_redis and self.redis_client:
                value = await self.redis_client.get(key)
                if value is None:
                    return None
                
                # Try to parse as JSON
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            else:
                return await self._get_local(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to get key '{key}': {e}")
            log_data_operation("GET", "redis", success=False, error=str(e))
            
            # Fallback to local storage
            if self.use_redis:
                logger.warning("⚠️  Falling back to local storage for this operation")
                return await self._get_local(key)
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key. Returns True if successful."""
        try:
            if self.use_redis and self.redis_client:
                result = await self.redis_client.delete(key)
                log_data_operation("DELETE", "redis", success=True)
                return bool(result)
            else:
                return await self._delete_local(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to delete key '{key}': {e}")
            log_data_operation("DELETE", "redis", success=False, error=str(e))
            
            # Fallback to local storage
            if self.use_redis:
                logger.warning("⚠️  Falling back to local storage for this operation")
                return await self._delete_local(key)
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            if self.use_redis and self.redis_client:
                return bool(await self.redis_client.exists(key))
            else:
                return await self._exists_local(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to check existence of key '{key}': {e}")
            return False
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern."""
        try:
            if self.use_redis and self.redis_client:
                return await self.redis_client.keys(pattern)
            else:
                return await self._keys_local(pattern)
                
        except Exception as e:
            logger.error(f"❌ Failed to get keys with pattern '{pattern}': {e}")
            return []
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment a numeric value. Returns new value."""
        try:
            if self.use_redis and self.redis_client:
                return await self.redis_client.incrby(key, amount)
            else:
                return await self._increment_local(key, amount)
                
        except Exception as e:
            logger.error(f"❌ Failed to increment key '{key}': {e}")
            return 0
    
    async def set_hash(self, key: str, field: str, value: Any) -> bool:
        """Set a field in a hash."""
        try:
            if self.use_redis and self.redis_client:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                await self.redis_client.hset(key, field, value)
                return True
            else:
                return await self._set_hash_local(key, field, value)
                
        except Exception as e:
            logger.error(f"❌ Failed to set hash field '{key}.{field}': {e}")
            return False
    
    async def get_hash(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        try:
            if self.use_redis and self.redis_client:
                value = await self.redis_client.hget(key, field)
                if value is None:
                    return None
                
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            else:
                return await self._get_hash_local(key, field)
                
        except Exception as e:
            logger.error(f"❌ Failed to get hash field '{key}.{field}': {e}")
            return None
    
    async def get_all_hash(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        try:
            if self.use_redis and self.redis_client:
                hash_data = await self.redis_client.hgetall(key)
                result = {}
                for field, value in hash_data.items():
                    try:
                        result[field] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[field] = value
                return result
            else:
                return await self._get_all_hash_local(key)
                
        except Exception as e:
            logger.error(f"❌ Failed to get all hash fields for '{key}': {e}")
            return {}
    
    # Local storage fallback methods
    async def _set_local(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set value in local file storage."""
        try:
            file_path = self.fallback_path / f"{key_to_filename(key)}.json"
            data = {
                "value": value,
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(seconds=expire)).isoformat() if expire else None
            }
            async with aiofiles.open(file_path, 'w') as f:
                await f.write(json.dumps(data, default=str))
            log_data_operation("SET", "local_file", success=True)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to set local file '{key}': {e}")
            log_data_operation("SET", "local_file", success=False, error=str(e))
            return False

    async def _get_local(self, key: str) -> Optional[Any]:
        """Get value from local file storage."""
        try:
            file_path = self.fallback_path / f"{key_to_filename(key)}.json"
            if not file_path.exists():
                return None
            async with aiofiles.open(file_path, 'r') as f:
                content = await f.read()
                data = json.loads(content)
            # Check expiration
            if data.get("expires_at"):
                expires_at = datetime.fromisoformat(data["expires_at"])
                if datetime.now() > expires_at:
                    await self._delete_local(key)
                    return None
            return data["value"]
        except Exception as e:
            logger.error(f"❌ Failed to get local file '{key}': {e}")
            return None

    async def _delete_local(self, key: str) -> bool:
        """Delete local file."""
        try:
            file_path = self.fallback_path / f"{key_to_filename(key)}.json"
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete local file '{key}': {e}")
            return False

    async def _exists_local(self, key: str) -> bool:
        """Check if local file exists."""
        file_path = self.fallback_path / f"{key_to_filename(key)}.json"
        return file_path.exists()

    async def _keys_local(self, pattern: str = "*") -> List[str]:
        """Get local file keys matching pattern."""
        try:
            keys = []
            for file_path in self.fallback_path.glob("*.json"):
                key = file_path.stem
                if pattern == "*" or key.startswith(pattern.replace("*", "")):
                    keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"❌ Failed to get local keys: {e}")
            return []

    
    async def _increment_local(self, key: str, amount: int = 1) -> int:
        """Increment local file value."""
        try:
            current_value = await self._get_local(key) or 0
            new_value = int(current_value) + amount
            await self._set_local(key, new_value)
            return new_value
        except Exception as e:
            logger.error(f"❌ Failed to increment local key '{key}': {e}")
            return 0
    
    async def _set_hash_local(self, key: str, field: str, value: Any) -> bool:
        """Set hash field in local storage."""
        try:
            hash_data = await self._get_local(key) or {}
            hash_data[field] = value
            return await self._set_local(key, hash_data)
        except Exception as e:
            logger.error(f"❌ Failed to set local hash '{key}.{field}': {e}")
            return False
    
    async def _get_hash_local(self, key: str, field: str) -> Optional[Any]:
        """Get hash field from local storage."""
        try:
            hash_data = await self._get_local(key) or {}
            return hash_data.get(field)
        except Exception as e:
            logger.error(f"❌ Failed to get local hash '{key}.{field}': {e}")
            return None
    
    async def _get_all_hash_local(self, key: str) -> Dict[str, Any]:
        """Get all hash fields from local storage."""
        try:
            return await self._get_local(key) or {}
        except Exception as e:
            logger.error(f"❌ Failed to get all local hash fields for '{key}': {e}")
            return {}

# Global data client instance
data_client = AureliusDataClient()

async def init_data_client(redis_url: Optional[str] = None, fallback_path: str = "data/") -> bool:
    """Initialize the global data client."""
    global data_client
    data_client = AureliusDataClient(redis_url, fallback_path)
    return await data_client.connect()

async def close_data_client():
    """Close the global data client."""
    if data_client:
        await data_client.disconnect()
