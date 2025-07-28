"""
AURELIUS Rate Limiting Module
Handles API rate limiting for social media platforms with Redis/local storage.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum

from ..db.redis_client import data_client
from ..logging_config import get_logger, log_rate_limit

logger = get_logger("RATE_LIMIT")

class RateLimitPeriod(Enum):
    """Rate limit time periods."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class RateLimitResult(Enum):
    """Rate limit check results."""
    ALLOWED = "allowed"
    LIMIT_REACHED = "limit_reached"
    LIMIT_EXCEEDED = "limit_exceeded"

class AureliusRateLimiter:
    """
    Async rate limiter with Redis/local storage backend.
    Supports multiple platforms and time periods.
    """
    
    def __init__(self):
        self.platform_limits = {
            'twitter': {
                RateLimitPeriod.HOURLY: 5,
                RateLimitPeriod.DAILY: 50
            },
            'mastodon': {
                RateLimitPeriod.HOURLY: 10,
                RateLimitPeriod.DAILY: 100
            },
            'discord': {
                RateLimitPeriod.HOURLY: 20,
                RateLimitPeriod.DAILY: 200
            }
        }
    
    def _get_time_window_key(self, platform: str, period: RateLimitPeriod, action: str = "post") -> str:
        """Generate Redis key for rate limit tracking."""
        now = datetime.now()
        
        if period == RateLimitPeriod.HOURLY:
            time_key = now.strftime("%Y-%m-%d-%H")
        elif period == RateLimitPeriod.DAILY:
            time_key = now.strftime("%Y-%m-%d")
        elif period == RateLimitPeriod.WEEKLY:
            # Get Monday of current week
            monday = now - timedelta(days=now.weekday())
            time_key = monday.strftime("%Y-W%U")
        else:  # MONTHLY
            time_key = now.strftime("%Y-%m")
        
        return f"rate_limit:{platform}:{action}:{period.value}:{time_key}"
    
    def _get_ttl_seconds(self, period: RateLimitPeriod) -> int:
        """Get TTL in seconds for the rate limit period."""
        if period == RateLimitPeriod.HOURLY:
            return 3600  # 1 hour
        elif period == RateLimitPeriod.DAILY:
            return 86400  # 24 hours
        elif period == RateLimitPeriod.WEEKLY:
            return 604800  # 7 days
        else:  # MONTHLY
            return 2592000  # 30 days
    
    async def check_rate_limit(
        self, 
        platform: str, 
        action: str = "post", 
        period: RateLimitPeriod = RateLimitPeriod.HOURLY
    ) -> Tuple[RateLimitResult, int, int]:
        """
        Check if action is within rate limits.
        Returns (result, current_count, limit).
        """
        try:
            platform_lower = platform.lower()
            
            # Get limit for platform and period
            if platform_lower not in self.platform_limits:
                logger.warning(f"⚠️  Unknown platform for rate limiting: {platform}")
                return RateLimitResult.ALLOWED, 0, 999999
            
            if period not in self.platform_limits[platform_lower]:
                logger.warning(f"⚠️  No rate limit configured for {platform} {period.value}")
                return RateLimitResult.ALLOWED, 0, 999999
            
            limit = self.platform_limits[platform_lower][period]
            key = self._get_time_window_key(platform_lower, period, action)
            
            # Get current count
            current_count = await data_client.get(key) or 0
            current_count = int(current_count)
            
            # Log rate limit status
            log_rate_limit(platform, f"{period.value} {action}", current_count, limit)
            
            # Check limits
            if current_count >= limit:
                logger.warning(f"🚨 Rate limit exceeded for {platform} {period.value} {action}: {current_count}/{limit}")
                return RateLimitResult.LIMIT_EXCEEDED, current_count, limit
            elif current_count >= limit * 0.9:  # 90% of limit
                logger.warning(f"⚠️  Rate limit approaching for {platform} {period.value} {action}: {current_count}/{limit}")
                return RateLimitResult.LIMIT_REACHED, current_count, limit
            else:
                return RateLimitResult.ALLOWED, current_count, limit
                
        except Exception as e:
            logger.error(f"❌ Rate limit check failed for {platform} {action}: {e}")
            # Fail open - allow the action but log the error
            return RateLimitResult.ALLOWED, 0, 999999
    
    async def increment_usage(
        self, 
        platform: str, 
        action: str = "post", 
        period: RateLimitPeriod = RateLimitPeriod.HOURLY,
        amount: int = 1
    ) -> int:
        """
        Increment usage counter for platform/action/period.
        Returns new count.
        """
        try:
            platform_lower = platform.lower()
            key = self._get_time_window_key(platform_lower, period, action)
            ttl = self._get_ttl_seconds(period)
            
            # Increment counter
            new_count = await data_client.increment(key, amount)
            
            # Set TTL if this is a new key
            if new_count == amount:
                # This is a new key, set expiration
                await data_client.set(key, new_count, expire=ttl)
            
            logger.info(f"📊 {platform} {period.value} {action} usage: {new_count}")
            return new_count
            
        except Exception as e:
            logger.error(f"❌ Failed to increment usage for {platform} {action}: {e}")
            return 0
    
    async def get_usage_stats(self, platform: str, action: str = "post") -> Dict[str, Dict[str, int]]:
        """
        Get current usage statistics for all periods.
        Returns dict with period -> {current, limit, remaining, percentage}.
        """
        stats = {}
        platform_lower = platform.lower()
        
        if platform_lower not in self.platform_limits:
            return stats
        
        for period in self.platform_limits[platform_lower]:
            try:
                key = self._get_time_window_key(platform_lower, period, action)
                current = await data_client.get(key) or 0
                current = int(current)
                limit = self.platform_limits[platform_lower][period]
                remaining = max(0, limit - current)
                percentage = (current / limit * 100) if limit > 0 else 0
                
                stats[period.value] = {
                    'current': current,
                    'limit': limit,
                    'remaining': remaining,
                    'percentage': round(percentage, 1)
                }
                
            except Exception as e:
                logger.error(f"❌ Failed to get usage stats for {platform} {period.value}: {e}")
                stats[period.value] = {
                    'current': 0,
                    'limit': 0,
                    'remaining': 0,
                    'percentage': 0
                }
        
        return stats
    
    async def reset_usage(self, platform: str, action: str = "post", period: Optional[RateLimitPeriod] = None) -> bool:
        """
        Reset usage counters. If period is None, resets all periods.
        Returns True if successful.
        """
        try:
            platform_lower = platform.lower()
            
            if platform_lower not in self.platform_limits:
                return False
            
            periods_to_reset = [period] if period else list(self.platform_limits[platform_lower].keys())
            
            for p in periods_to_reset:
                key = self._get_time_window_key(platform_lower, p, action)
                await data_client.delete(key)
                logger.info(f"🔄 Reset {platform} {p.value} {action} usage counter")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to reset usage for {platform} {action}: {e}")
            return False
    
    async def update_platform_limits(self, platform: str, limits: Dict[RateLimitPeriod, int]) -> bool:
        """
        Update rate limits for a platform.
        Returns True if successful.
        """
        try:
            platform_lower = platform.lower()
            
            if platform_lower not in self.platform_limits:
                self.platform_limits[platform_lower] = {}
            
            self.platform_limits[platform_lower].update(limits)
            
            logger.info(f"✅ Updated rate limits for {platform}: {limits}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update rate limits for {platform}: {e}")
            return False
    
    async def is_action_allowed(
        self, 
        platform: str, 
        action: str = "post",
        check_all_periods: bool = True
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if action is allowed across all configured periods.
        Returns (allowed, details_dict).
        """
        platform_lower = platform.lower()
        
        if platform_lower not in self.platform_limits:
            return True, {'error': f'Unknown platform: {platform}'}
        
        details = {
            'platform': platform,
            'action': action,
            'allowed': True,
            'periods': {}
        }
        
        periods_to_check = list(self.platform_limits[platform_lower].keys()) if check_all_periods else [RateLimitPeriod.HOURLY]
        
        for period in periods_to_check:
            result, current, limit = await self.check_rate_limit(platform, action, period)
            
            period_details = {
                'result': result.value,
                'current': current,
                'limit': limit,
                'remaining': max(0, limit - current),
                'percentage': round((current / limit * 100) if limit > 0 else 0, 1)
            }
            
            details['periods'][period.value] = period_details
            
            # If any period is exceeded, action is not allowed
            if result == RateLimitResult.LIMIT_EXCEEDED:
                details['allowed'] = False
                details['blocked_by'] = period.value
        
        return details['allowed'], details
    
    async def execute_with_rate_limit(
        self, 
        platform: str, 
        action: str, 
        func, 
        *args, 
        **kwargs
    ):
        """
        Execute a function with rate limit checking.
        Increments counters only if function succeeds.
        """
        # Check if action is allowed
        allowed, details = await self.is_action_allowed(platform, action)
        
        if not allowed:
            blocked_by = details.get('blocked_by', 'unknown')
            raise RateLimitExceeded(f"Rate limit exceeded for {platform} {action} ({blocked_by})")
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Increment usage counters for all periods
            platform_lower = platform.lower()
            if platform_lower in self.platform_limits:
                for period in self.platform_limits[platform_lower]:
                    await self.increment_usage(platform, action, period)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Function execution failed for {platform} {action}: {e}")
            raise

class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    pass

# Global rate limiter instance
rate_limiter = AureliusRateLimiter()

async def check_platform_rate_limit(platform: str, action: str = "post") -> bool:
    """
    Quick function to check if platform action is allowed.
    Returns True if allowed, False if rate limited.
    """
    allowed, details = await rate_limiter.is_action_allowed(platform, action)
    
    if not allowed:
        logger.warning(f"🚨 Rate limit blocked {platform} {action}: {details}")
    
    return allowed

async def increment_platform_usage(platform: str, action: str = "post") -> None:
    """
    Quick function to increment usage for all periods.
    Call this after successful API calls.
    """
    platform_lower = platform.lower()
    if platform_lower in rate_limiter.platform_limits:
        for period in rate_limiter.platform_limits[platform_lower]:
            await rate_limiter.increment_usage(platform, action, period)

async def get_platform_usage_summary(platform: str) -> Dict[str, any]:
    """Get usage summary for a platform."""
    return await rate_limiter.get_usage_stats(platform, "post")

async def wait_for_rate_limit_reset(platform: str, period: RateLimitPeriod = RateLimitPeriod.HOURLY) -> int:
    """
    Calculate seconds to wait until rate limit resets.
    Returns seconds to wait.
    """
    now = datetime.now()
    
    if period == RateLimitPeriod.HOURLY:
        next_reset = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    elif period == RateLimitPeriod.DAILY:
        next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    elif period == RateLimitPeriod.WEEKLY:
        days_until_monday = (7 - now.weekday()) % 7
        next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
    else:  # MONTHLY
        if now.month == 12:
            next_reset = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_reset = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    wait_seconds = int((next_reset - now).total_seconds())
    logger.info(f"⏰ {platform} {period.value} rate limit resets in {wait_seconds} seconds")
    
    return wait_seconds
