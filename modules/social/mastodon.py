"""
AURELIUS Mastodon Integration Module
Handles Mastodon API integration for automated posting and engagement.
"""

import asyncio
from mastodon import Mastodon
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import json
import aiohttp

from ...config import config
from ...logging_config import get_logger, log_social_activity, log_api_call
from ...utils.security import sanitize_and_prepare_content, validate_and_sanitize_input
from ...utils.rate_limit import rate_limiter, check_platform_rate_limit, increment_platform_usage
from ...db.redis_client import data_client

logger = get_logger("MASTODON")

class AureliusMastodon:
    """
    Mastodon API integration for automated posting, engagement, and interaction management.
    Supports posting, replies, mentions, and analytics.
    """
    
    def __init__(self):
        self.access_token = config.MASTODON_ACCESS_TOKEN
        self.api_base_url = config.MASTODON_API_BASE_URL
        
        # Initialize Mastodon client
        self.mastodon = None
        self._initialize_client()
        
        # Track posted content and interactions
        self.posted_content_key = "mastodon:posted_content"
        self.mentions_processed_key = "mastodon:mentions_processed"
        self.notifications_key = "mastodon:notifications"
    
    def _initialize_client(self):
        """Initialize Mastodon API client."""
        try:
            self.mastodon = Mastodon(
                access_token=self.access_token,
                api_base_url=self.api_base_url,
                request_timeout=30
            )
            
            # Test connection
            account = self.mastodon.me()
            logger.info(f"✅ Mastodon client initialized | Account: @{account['username']}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Mastodon client: {e}")
            raise
    
    async def post_status(
        self,
        content: str,
        visibility: str = "public",
        in_reply_to_id: Optional[str] = None,
        media_ids: Optional[List[str]] = None,
        sensitive: bool = False,
        spoiler_text: Optional[str] = None,
        poll_options: Optional[List[str]] = None,
        poll_expires_in: int = 86400
    ) -> Dict[str, Any]:
        """
        Post a status (toot) to Mastodon.
        Returns status data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("mastodon", "post"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "retry_after": 3600
                }
            
            # Sanitize content
            # Sanitize content
            sanitized_content = sanitize_and_prepare_content(content, "mastodon")
            if not sanitized_content:
                return {
                    "success": False,
                    "error": "Content failed sanitization"
                }

            # Limitar a 500 caracteres (Mastodon hard limit)
            sanitized_content = sanitized_content.strip()
            if len(sanitized_content) > 500:
                # Corta en el último espacio si es posible, si no solo recorta
                last_space = sanitized_content[:500].rfind(' ')
                if last_space != -1 and last_space > 0:
                    sanitized_content = sanitized_content[:last_space]
                else:
                    sanitized_content = sanitized_content[:500]

            # Check for duplicate content
            if await self._is_duplicate_content(sanitized_content):
                logger.warning("⚠️  Duplicate content detected, skipping post")
                return {
                    "success": False,
                    "error": "Duplicate content"
                }

            
            # Prepare status parameters
            status_params = {
                "status": sanitized_content,
                "visibility": visibility,
                "sensitive": sensitive
            }
            
            if in_reply_to_id:
                status_params["in_reply_to_id"] = in_reply_to_id
            
            if media_ids:
                status_params["media_ids"] = media_ids
            
            if spoiler_text:
                status_params["spoiler_text"] = sanitize_and_prepare_content(spoiler_text, "mastodon")
            
            if poll_options and len(poll_options) >= 2:
                status_params["poll"] = {
                    "options": poll_options[:4],  # Max 4 options
                    "expires_in": min(poll_expires_in, 2629746)  # Max 30 days
                }
            
            log_api_call("Mastodon", "POST /api/v1/statuses", "POST")
            
            # Post status using sync client (run in thread pool)
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self.mastodon.status_post(**status_params)
            )
            
            if status:
                status_id = status["id"]
                status_url = status["url"]
                
                # Store posted content to prevent duplicates
                await self._store_posted_content(sanitized_content, status_id)
                
                # Increment usage counters
                await increment_platform_usage("mastodon", "post")
                
                log_social_activity("Mastodon", "status_posted", sanitized_content[:50], success=True)
                log_api_call("Mastodon", "POST /api/v1/statuses", "POST", status=200)
                
                result = {
                    "success": True,
                    "status_id": status_id,
                    "status_url": status_url,
                    "content": sanitized_content,
                    "visibility": visibility,
                    "timestamp": datetime.now().isoformat(),
                    "favourites_count": status.get("favourites_count", 0),
                    "reblogs_count": status.get("reblogs_count", 0),
                    "replies_count": status.get("replies_count", 0)
                }
                
                logger.info(f"✅ Status posted successfully | ID: {status_id}")
                return result
            else:
                error_msg = "No data in Mastodon API response"
                log_social_activity("Mastodon", "status_posted", sanitized_content[:50], success=False, error=error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            error_msg = f"Failed to post status: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Mastodon", "status_posted", content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def get_notifications(
        self,
        limit: int = 20,
        since_id: Optional[str] = None,
        notification_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get notifications (mentions, follows, favourites, etc.).
        Returns list of notification data.
        """
        try:
            log_api_call("Mastodon", "GET /api/v1/notifications", "GET")
            
            # Prepare parameters
            params = {"limit": min(limit, 40)}
            
            if since_id:
                params["since_id"] = since_id
            
            if notification_types:
                params["types"] = notification_types
            
            # Get notifications using sync client
            loop = asyncio.get_event_loop()
            notifications = await loop.run_in_executor(
                None,
                lambda: self.mastodon.notifications(**params)
            )
            
            if not notifications:
                logger.info("📭 No new notifications found")
                return []
            
            processed_notifications = []
            for notification in notifications:
                notification_data = {
                    "id": notification["id"],
                    "type": notification["type"],
                    "created_at": notification["created_at"].isoformat() if notification.get("created_at") else None,
                    "account": {
                        "id": notification["account"]["id"],
                        "username": notification["account"]["username"],
                        "display_name": notification["account"]["display_name"],
                        "url": notification["account"]["url"]
                    },
                    "processed": False
                }
                
                # Add status data if present
                if notification.get("status"):
                    status = notification["status"]
                    notification_data["status"] = {
                        "id": status["id"],
                        "content": status["content"],
                        "url": status["url"],
                        "visibility": status["visibility"],
                        "created_at": status["created_at"].isoformat() if status.get("created_at") else None
                    }
                
                processed_notifications.append(notification_data)
            
            log_api_call("Mastodon", "GET /api/v1/notifications", "GET", status=200)
            logger.info(f"📬 Retrieved {len(processed_notifications)} notifications")
            
            return processed_notifications
            
        except Exception as e:
            error_msg = f"Failed to get notifications: {e}"
            logger.error(f"❌ {error_msg}")
            log_api_call("Mastodon", "GET /api/v1/notifications", "GET", error=error_msg)
            return []
    
    async def reply_to_status(self, status_id: str, reply_content: str, visibility: str = "public") -> Dict[str, Any]:
        """
        Reply to a specific status.
        Returns reply data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("mastodon", "reply"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded for replies"
                }
            
            # Post reply
            result = await self.post_status(
                content=reply_content,
                visibility=visibility,
                in_reply_to_id=status_id
            )
            
            if result["success"]:
                logger.info(f"✅ Reply posted to status {status_id}")
                log_social_activity("Mastodon", "reply_posted", reply_content[:50], success=True)
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to reply to status {status_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Mastodon", "reply_posted", reply_content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def favourite_status(self, status_id: str) -> Dict[str, Any]:
        """
        Favourite (like) a status.
        Returns success status.
        """
        try:
            log_api_call("Mastodon", "POST /api/v1/statuses/:id/favourite", "POST")
            
            # Favourite the status
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self.mastodon.status_favourite(status_id)
            )
            
            if status:
                log_social_activity("Mastodon", "status_favourited", f"Status {status_id}", success=True)
                log_api_call("Mastodon", "POST /api/v1/statuses/:id/favourite", "POST", status=200)
                logger.info(f"✅ Favourited status {status_id}")
                
                return {
                    "success": True,
                    "status_id": status_id,
                    "favourites_count": status.get("favourites_count", 0),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "Favourite operation failed"
                }
                
        except Exception as e:
            error_msg = f"Failed to favourite status {status_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Mastodon", "status_favourited", f"Status {status_id}", success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def boost_status(self, status_id: str, visibility: str = "public") -> Dict[str, Any]:
        """
        Boost (reblog) a status.
        Returns boost data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("mastodon", "boost"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded for boosts"
                }
            
            log_api_call("Mastodon", "POST /api/v1/statuses/:id/reblog", "POST")
            
            # Boost the status
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self.mastodon.status_reblog(status_id, visibility=visibility)
            )
            
            if status:
                log_social_activity("Mastodon", "status_boosted", f"Status {status_id}", success=True)
                log_api_call("Mastodon", "POST /api/v1/statuses/:id/reblog", "POST", status=200)
                logger.info(f"✅ Boosted status {status_id}")
                
                return {
                    "success": True,
                    "status_id": status_id,
                    "boost_id": status["id"],
                    "reblogs_count": status.get("reblogs_count", 0),
                    "visibility": visibility,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "Boost operation failed"
                }
                
        except Exception as e:
            error_msg = f"Failed to boost status {status_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Mastodon", "status_boosted", f"Status {status_id}", success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def get_status_analytics(self, status_id: str) -> Dict[str, Any]:
        """
        Get analytics data for a status.
        Returns engagement metrics.
        """
        try:
            log_api_call("Mastodon", "GET /api/v1/statuses/:id", "GET")
            
            # Get status details
            loop = asyncio.get_event_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self.mastodon.status(status_id)
            )
            
            if not status:
                return {
                    "success": False,
                    "error": "Status not found"
                }
            
            analytics = {
                "success": True,
                "status_id": status_id,
                "metrics": {
                    "favourites_count": status.get("favourites_count", 0),
                    "reblogs_count": status.get("reblogs_count", 0),
                    "replies_count": status.get("replies_count", 0)
                },
                "visibility": status.get("visibility", "unknown"),
                "created_at": status["created_at"].isoformat() if status.get("created_at") else None,
                "content_length": len(status.get("content", "")),
                "has_media": len(status.get("media_attachments", [])) > 0,
                "retrieved_at": datetime.now().isoformat()
            }
            
            # Calculate total engagement
            total_engagement = (
                analytics["metrics"]["favourites_count"] +
                analytics["metrics"]["reblogs_count"] +
                analytics["metrics"]["replies_count"]
            )
            analytics["total_engagement"] = total_engagement
            
            log_api_call("Mastodon", "GET /api/v1/statuses/:id", "GET", status=200)
            logger.info(f"📊 Retrieved analytics for status {status_id}")
            
            return analytics
            
        except Exception as e:
            error_msg = f"Failed to get analytics for status {status_id}: {e}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
    
    async def search_statuses(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for statuses containing specific terms.
        Returns list of matching statuses.
        """
        try:
            log_api_call("Mastodon", "GET /api/v2/search", "GET")
            
            # Sanitize search query
            sanitized_query = validate_and_sanitize_input(query, "search_query")
            
            # Search for statuses
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None,
                lambda: self.mastodon.search_v2(sanitized_query, result_type="statuses", limit=min(limit, 40))
            )
            
            if not search_results or not search_results.get("statuses"):
                logger.info(f"🔍 No statuses found for query: {sanitized_query}")
                return []
            
            processed_statuses = []
            for status in search_results["statuses"]:
                status_data = {
                    "id": status["id"],
                    "content": status["content"],
                    "url": status["url"],
                    "created_at": status["created_at"].isoformat() if status.get("created_at") else None,
                    "account": {
                        "username": status["account"]["username"],
                        "display_name": status["account"]["display_name"],
                        "url": status["account"]["url"]
                    },
                    "metrics": {
                        "favourites_count": status.get("favourites_count", 0),
                        "reblogs_count": status.get("reblogs_count", 0),
                        "replies_count": status.get("replies_count", 0)
                    },
                    "visibility": status.get("visibility", "unknown")
                }
                processed_statuses.append(status_data)
            
            log_api_call("Mastodon", "GET /api/v2/search", "GET", status=200)
            logger.info(f"🔍 Found {len(processed_statuses)} statuses for query: {sanitized_query}")
            
            return processed_statuses
            
        except Exception as e:
            error_msg = f"Failed to search statuses for '{query}': {e}"
            logger.error(f"❌ {error_msg}")
            return []
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Get authenticated account information.
        Returns account details.
        """
        try:
            log_api_call("Mastodon", "GET /api/v1/accounts/verify_credentials", "GET")
            
            # Get account info
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self.mastodon.me()
            )
            
            if account:
                account_info = {
                    "success": True,
                    "id": account["id"],
                    "username": account["username"],
                    "display_name": account["display_name"],
                    "url": account["url"],
                    "followers_count": account.get("followers_count", 0),
                    "following_count": account.get("following_count", 0),
                    "statuses_count": account.get("statuses_count", 0),
                    "created_at": account["created_at"].isoformat() if account.get("created_at") else None,
                    "note": account.get("note", ""),
                    "avatar": account.get("avatar", ""),
                    "header": account.get("header", ""),
                    "locked": account.get("locked", False),
                    "bot": account.get("bot", False)
                }
                
                log_api_call("Mastodon", "GET /api/v1/accounts/verify_credentials", "GET", status=200)
                logger.info(f"✅ Retrieved account info for @{account['username']}")
                
                return account_info
            else:
                return {
                    "success": False,
                    "error": "Could not retrieve account information"
                }
                
        except Exception as e:
            error_msg = f"Failed to get account info: {e}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
    
    async def _is_duplicate_content(self, content: str) -> bool:
        """Check if content has been posted recently."""
        try:
            # Get recent posted content
            recent_posts = await data_client.get(self.posted_content_key) or []
            
            # Check for exact matches or very similar content
            content_lower = content.lower().strip()
            for post in recent_posts[-50:]:  # Check last 50 posts
                if post.get("content", "").lower().strip() == content_lower:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking duplicate content: {e}")
            return False
    
    async def _store_posted_content(self, content: str, status_id: str):
        """Store posted content to prevent duplicates."""
        try:
            recent_posts = await data_client.get(self.posted_content_key) or []
            
            # Add new post
            post_data = {
                "content": content,
                "status_id": status_id,
                "timestamp": datetime.now().isoformat()
            }
            
            recent_posts.append(post_data)
            
            # Keep only last 100 posts
            if len(recent_posts) > 100:
                recent_posts = recent_posts[-100:]
            
            # Store with 7-day expiration
            await data_client.set(self.posted_content_key, recent_posts, expire=604800)
            
        except Exception as e:
            logger.error(f"❌ Error storing posted content: {e}")

# Global Mastodon service instance
mastodon_service = AureliusMastodon()

async def post_to_mastodon(content: str, **kwargs) -> Dict[str, Any]:
    """Quick function to post to Mastodon."""
    return await mastodon_service.post_status(content, **kwargs)

async def reply_to_mastodon_status(status_id: str, reply: str, **kwargs) -> Dict[str, Any]:
    """Quick function to reply to a Mastodon status."""
    return await mastodon_service.reply_to_status(status_id, reply, **kwargs)

async def get_mastodon_notifications(limit: int = 20) -> List[Dict[str, Any]]:
    """Quick function to get Mastodon notifications."""
    return await mastodon_service.get_notifications(limit=limit)

async def search_mastodon_content(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Quick function to search Mastodon content."""
    return await mastodon_service.search_statuses(query, limit)
