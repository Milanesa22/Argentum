"""
AURELIUS Twitter Integration Module
Handles Twitter/X API integration for automated posting and engagement.
"""

import asyncio
import tweepy
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import json

from ...config import config
from ...logging_config import get_logger, log_social_activity, log_api_call
from ...utils.security import sanitize_and_prepare_content, validate_and_sanitize_input
from ...utils.rate_limit import rate_limiter, check_platform_rate_limit, increment_platform_usage
from ...db.redis_client import data_client

logger = get_logger("TWITTER")

class AureliusTwitter:
    """
    Twitter/X API integration for automated posting, engagement, and DM management.
    Uses Twitter API v2 with proper rate limiting and error handling.
    """
    
    def __init__(self):
        self.api_key = config.TWITTER_API_KEY
        self.api_secret = config.TWITTER_API_SECRET
        self.access_token = config.TWITTER_ACCESS_TOKEN
        self.access_token_secret = config.TWITTER_ACCESS_TOKEN_SECRET
        self.bearer_token = config.TWITTER_BEARER_TOKEN
        
        # Initialize Twitter API clients
        self.client_v2 = None
        self.api_v1 = None
        self._initialize_clients()
        
        # Track posted content to avoid duplicates
        self.posted_content_key = "twitter:posted_content"
        self.mentions_processed_key = "twitter:mentions_processed"
        self.dm_conversations_key = "twitter:dm_conversations"
    
        # --- BLOQUE NUEVO: Control de bloqueo temporal por rate limit ---
    async def _set_blocked(self, seconds: int = 900):
        """
        Bloquea temporalmente las llamadas a Twitter por X segundos (por default, 15 min).
        """
        await data_client.set("twitter:blocked_until", (datetime.now() + timedelta(seconds=seconds)).timestamp(), expire=seconds)

    async def _is_blocked(self) -> bool:
        """
        Devuelve True si el sistema está temporalmente bloqueado para llamadas a Twitter.
        """
        blocked_until = await data_client.get("twitter:blocked_until")
        if not blocked_until:
            return False
        try:
            return datetime.now().timestamp() < float(blocked_until)
        except Exception:
            return False

    def _initialize_clients(self):
        """Initialize Twitter API clients (v1.1 and v2)."""
        try:
            # Twitter API v2 client (for most operations)
            self.client_v2 = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Twitter API v1.1 (for some legacy operations)
            auth = tweepy.OAuth1UserHandler(
                self.api_key,
                self.api_secret,
                self.access_token,
                self.access_token_secret
            )
            self.api_v1 = tweepy.API(auth, wait_on_rate_limit=True)
            
            logger.info("✅ Twitter API clients initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Twitter API clients: {e}")
            raise
    
    async def post_tweet(
        self,
        content: str,
        reply_to_id: Optional[str] = None,
        media_ids: Optional[List[str]] = None,
        poll_options: Optional[List[str]] = None,
        poll_duration_minutes: int = 1440
    ) -> Dict[str, Any]:
        """
        Post a tweet with optional media, polls, or as a reply.
        Returns tweet data or error information.
        """
        # --- Si está bloqueado, saltea ---
        if await self._is_blocked():
            logger.warning("⏳ Twitter temporalmente bloqueado por rate limit. Saltando post_tweet().")
            return {"success": False, "error": "Twitter temporalmente bloqueado por rate limit"}
        try:
            # Check rate limits
            if not await check_platform_rate_limit("twitter", "post"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "retry_after": 3600
                }
            
            # Sanitize content
            sanitized_content = sanitize_and_prepare_content(content, "twitter")
            if not sanitized_content:
                return {
                    "success": False,
                    "error": "Content failed sanitization"
                }
            
            # Check for duplicate content
            if await self._is_duplicate_content(sanitized_content):
                logger.warning("⚠️  Duplicate content detected, skipping post")
                return {
                    "success": False,
                    "error": "Duplicate content"
                }
            
            # Prepare tweet parameters
            tweet_params = {"text": sanitized_content}
            
            if reply_to_id:
                tweet_params["in_reply_to_tweet_id"] = reply_to_id
            
            if media_ids:
                tweet_params["media_ids"] = media_ids
            
            if poll_options and len(poll_options) >= 2:
                tweet_params["poll"] = {
                    "options": poll_options[:4],
                    "duration_minutes": min(poll_duration_minutes, 10080)
                }
            
            log_api_call("Twitter", "POST /tweets", "POST")
            
            # Post tweet
            response = self.client_v2.create_tweet(**tweet_params)
            
            if response.data:
                tweet_id = response.data["id"]
                tweet_url = f"https://twitter.com/user/status/{tweet_id}"
                
                # Store posted content to prevent duplicates
                await self._store_posted_content(sanitized_content, tweet_id)
                
                # Increment usage counters
                await increment_platform_usage("twitter", "post")
                
                log_social_activity("Twitter", "tweet_posted", sanitized_content[:50], success=True)
                log_api_call("Twitter", "POST /tweets", "POST", status=200)
                
                result = {
                    "success": True,
                    "tweet_id": tweet_id,
                    "tweet_url": tweet_url,
                    "content": sanitized_content,
                    "timestamp": datetime.now().isoformat()
                }
                
                logger.info(f"✅ Tweet posted successfully | ID: {tweet_id}")
                return result
            else:
                error_msg = "No data in Twitter API response"
                log_social_activity("Twitter", "tweet_posted", sanitized_content[:50], success=False, error=error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except tweepy.TooManyRequests:
            logger.error("❌ Twitter API rate limit (post_tweet) | Bloqueando temporalmente el sistema Twitter.")
            await self._set_blocked()
            return {
                "success": False,
                "error": "Twitter API rate limit exceeded",
                "retry_after": 900
            }
        except Exception as e:
            error_msg = f"Failed to post tweet: {e}"
            logger.error(f"❌ {error_msg}")
            if "rate limit" in str(e).lower():
                await self._set_blocked()
            log_social_activity("Twitter", "tweet_posted", content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    
    async def get_mentions(self, since_id: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent mentions of the authenticated user.
        Returns list of mention data.
        """
        # --- Si está bloqueado, saltea ---
        if await self._is_blocked():
            logger.warning("⏳ Twitter temporalmente bloqueado por rate limit. Saltando get_mentions().")
            return []
        try:
            log_api_call("Twitter", "GET /users/:id/mentions", "GET")
            
            # Get user ID first
            me = self.client_v2.get_me()
            if not me.data:
                logger.error("❌ Could not get authenticated user info")
                return []
            
            user_id = me.data.id
            
            # Get mentions
            params = {
                "max_results": min(max_results, 100),
                "tweet_fields": "created_at,author_id,conversation_id,public_metrics",
                "user_fields": "username,name,verified"
            }
            
            if since_id:
                params["since_id"] = since_id
            
            mentions = self.client_v2.get_users_mentions(user_id, **params)
            
            if not mentions.data:
                logger.info("📭 No new mentions found")
                return []
            
            processed_mentions = []
            for tweet in mentions.data:
                mention_data = {
                    "id": tweet.id,
                    "text": tweet.text,
                    "author_id": tweet.author_id,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "conversation_id": tweet.conversation_id,
                    "public_metrics": tweet.public_metrics,
                    "processed": False
                }
                
                # Add author info if available
                if mentions.includes and "users" in mentions.includes:
                    for user in mentions.includes["users"]:
                        if user.id == tweet.author_id:
                            mention_data["author"] = {
                                "username": user.username,
                                "name": user.name,
                                "verified": getattr(user, "verified", False)
                            }
                            break
                
                processed_mentions.append(mention_data)
            
            log_api_call("Twitter", "GET /users/:id/mentions", "GET", status=200)
            logger.info(f"📬 Retrieved {len(processed_mentions)} mentions")
            
            return processed_mentions
            
        except tweepy.TooManyRequests:
            logger.error("❌ Twitter API rate limit (get_mentions) | Bloqueando temporalmente el sistema Twitter.")
            await self._set_blocked()
            return []
        except Exception as e:
            error_msg = f"Failed to get mentions: {e}"
            logger.error(f"❌ {error_msg}")
            # Si el error es de rate limit, bloquea igual por seguridad
            if "rate limit" in str(e).lower():
                await self._set_blocked()
            log_api_call("Twitter", "GET /users/:id/mentions", "GET", error=error_msg)
            return []

    
    async def reply_to_tweet(self, tweet_id: str, reply_content: str) -> Dict[str, Any]:
        """
        Reply to a specific tweet.
        Returns reply data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("twitter", "reply"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded for replies"
                }
            
            # Post reply
            result = await self.post_tweet(
                content=reply_content,
                reply_to_id=tweet_id
            )
            
            if result["success"]:
                logger.info(f"✅ Reply posted to tweet {tweet_id}")
                log_social_activity("Twitter", "reply_posted", reply_content[:50], success=True)
            
            return result
            
        except Exception as e:
            error_msg = f"Failed to reply to tweet {tweet_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Twitter", "reply_posted", reply_content[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def send_direct_message(self, recipient_username: str, message: str) -> Dict[str, Any]:
        """
        Send a direct message to a user.
        Returns DM data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("twitter", "dm"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded for DMs"
                }
            
            # Sanitize message
            sanitized_message = sanitize_and_prepare_content(message, "twitter")
            if not sanitized_message:
                return {
                    "success": False,
                    "error": "Message failed sanitization"
                }
            
            # Get recipient user ID
            try:
                user = self.client_v2.get_user(username=recipient_username)
                if not user.data:
                    return {
                        "success": False,
                        "error": f"User @{recipient_username} not found"
                    }
                recipient_id = user.data.id
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to find user @{recipient_username}: {e}"
                }
            
            log_api_call("Twitter", "POST /dm_conversations/with/:participant_id/messages", "POST")
            
            # Send DM using v1.1 API (v2 doesn't support DMs yet)
            dm = self.api_v1.send_direct_message(
                recipient_id=recipient_id,
                text=sanitized_message
            )
            
            # Store conversation info
            await self._store_dm_conversation(recipient_id, recipient_username, sanitized_message)
            
            log_social_activity("Twitter", "dm_sent", sanitized_message[:50], success=True)
            log_api_call("Twitter", "POST /dm_conversations/with/:participant_id/messages", "POST", status=200)
            
            result = {
                "success": True,
                "dm_id": dm.id,
                "recipient": recipient_username,
                "message": sanitized_message,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"✅ DM sent to @{recipient_username}")
            return result
            
        except tweepy.Forbidden as e:
            error_msg = f"Cannot send DM to @{recipient_username}: {e}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Failed to send DM to @{recipient_username}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Twitter", "dm_sent", message[:50], success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    async def like_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """
        Like a tweet.
        Returns success status.
        """
        try:
            log_api_call("Twitter", "POST /users/:id/likes", "POST")
            
            # Get authenticated user
            me = self.client_v2.get_me()
            if not me.data:
                return {
                    "success": False,
                    "error": "Could not get authenticated user"
                }
            
            # Like the tweet
            response = self.client_v2.like(tweet_id)
            
            if response.data and response.data.get("liked"):
                log_social_activity("Twitter", "tweet_liked", f"Tweet {tweet_id}", success=True)
                log_api_call("Twitter", "POST /users/:id/likes", "POST", status=200)
                logger.info(f"✅ Liked tweet {tweet_id}")
                return {
                    "success": True,
                    "tweet_id": tweet_id,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": "Like operation failed"
                }
                
        except Exception as e:
            error_msg = f"Failed to like tweet {tweet_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Twitter", "tweet_liked", f"Tweet {tweet_id}", success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def retweet(self, tweet_id: str, quote_text: Optional[str] = None) -> Dict[str, Any]:
        """
        Retweet or quote tweet.
        Returns retweet data or error information.
        """
        try:
            # Check rate limits
            if not await check_platform_rate_limit("twitter", "retweet"):
                return {
                    "success": False,
                    "error": "Rate limit exceeded for retweets"
                }
            
            log_api_call("Twitter", "POST /users/:id/retweets", "POST")
            
            if quote_text:
                # Quote tweet
                sanitized_quote = sanitize_and_prepare_content(quote_text, "twitter")
                result = await self.post_tweet(
                    content=f"{sanitized_quote} https://twitter.com/user/status/{tweet_id}"
                )
                
                if result["success"]:
                    log_social_activity("Twitter", "quote_tweet", sanitized_quote[:50], success=True)
                    logger.info(f"✅ Quote tweeted {tweet_id}")
                
                return result
            else:
                # Regular retweet
                response = self.client_v2.retweet(tweet_id)
                
                if response.data and response.data.get("retweeted"):
                    log_social_activity("Twitter", "retweeted", f"Tweet {tweet_id}", success=True)
                    log_api_call("Twitter", "POST /users/:id/retweets", "POST", status=200)
                    logger.info(f"✅ Retweeted {tweet_id}")
                    
                    return {
                        "success": True,
                        "tweet_id": tweet_id,
                        "type": "retweet",
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "success": False,
                        "error": "Retweet operation failed"
                    }
                    
        except Exception as e:
            error_msg = f"Failed to retweet {tweet_id}: {e}"
            logger.error(f"❌ {error_msg}")
            log_social_activity("Twitter", "retweeted", f"Tweet {tweet_id}", success=False, error=error_msg)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def get_tweet_analytics(self, tweet_id: str) -> Dict[str, Any]:
        """
        Get analytics data for a tweet.
        Returns engagement metrics.
        """
        try:
            log_api_call("Twitter", "GET /tweets/:id", "GET")
            
            # Get tweet with metrics
            tweet = self.client_v2.get_tweet(
                tweet_id,
                tweet_fields=["public_metrics", "created_at", "author_id"]
            )
            
            if not tweet.data:
                return {
                    "success": False,
                    "error": "Tweet not found"
                }
            
            metrics = tweet.data.public_metrics
            
            analytics = {
                "success": True,
                "tweet_id": tweet_id,
                "metrics": {
                    "retweet_count": metrics.get("retweet_count", 0),
                    "like_count": metrics.get("like_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                    "quote_count": metrics.get("quote_count", 0),
                    "bookmark_count": metrics.get("bookmark_count", 0),
                    "impression_count": metrics.get("impression_count", 0)
                },
                "created_at": tweet.data.created_at.isoformat() if tweet.data.created_at else None,
                "engagement_rate": 0,
                "retrieved_at": datetime.now().isoformat()
            }
            
            # Calculate engagement rate
            impressions = analytics["metrics"]["impression_count"]
            if impressions > 0:
                total_engagements = (
                    analytics["metrics"]["like_count"] +
                    analytics["metrics"]["retweet_count"] +
                    analytics["metrics"]["reply_count"] +
                    analytics["metrics"]["quote_count"]
                )
                analytics["engagement_rate"] = round((total_engagements / impressions) * 100, 2)
            
            log_api_call("Twitter", "GET /tweets/:id", "GET", status=200)
            logger.info(f"📊 Retrieved analytics for tweet {tweet_id}")
            
            return analytics
            
        except Exception as e:
            error_msg = f"Failed to get analytics for tweet {tweet_id}: {e}"
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
    
    async def _store_posted_content(self, content: str, tweet_id: str):
        """Store posted content to prevent duplicates."""
        try:
            recent_posts = await data_client.get(self.posted_content_key) or []
            
            # Add new post
            post_data = {
                "content": content,
                "tweet_id": tweet_id,
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
    
    async def _store_dm_conversation(self, recipient_id: str, username: str, message: str):
        """Store DM conversation data."""
        try:
            conversations = await data_client.get(self.dm_conversations_key) or {}
            
            if recipient_id not in conversations:
                conversations[recipient_id] = {
                    "username": username,
                    "messages": [],
                    "last_contact": None
                }
            
            conversations[recipient_id]["messages"].append({
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "direction": "sent"
            })
            
            conversations[recipient_id]["last_contact"] = datetime.now().isoformat()
            
            # Keep only last 50 messages per conversation
            if len(conversations[recipient_id]["messages"]) > 50:
                conversations[recipient_id]["messages"] = conversations[recipient_id]["messages"][-50:]
            
            await data_client.set(self.dm_conversations_key, conversations, expire=2592000)  # 30 days
            
        except Exception as e:
            logger.error(f"❌ Error storing DM conversation: {e}")

# Global Twitter service instance
twitter_service = AureliusTwitter()

async def post_to_twitter(content: str, **kwargs) -> Dict[str, Any]:
    """Quick function to post to Twitter."""
    return await twitter_service.post_tweet(content, **kwargs)

async def reply_to_twitter_mention(tweet_id: str, reply: str) -> Dict[str, Any]:
    """Quick function to reply to a Twitter mention."""
    return await twitter_service.reply_to_tweet(tweet_id, reply)

async def send_twitter_dm(username: str, message: str) -> Dict[str, Any]:
    """Quick function to send a Twitter DM."""
    return await twitter_service.send_direct_message(username, message)

async def get_twitter_mentions(max_results: int = 10) -> List[Dict[str, Any]]:
    """Quick function to get Twitter mentions."""
    return await twitter_service.get_mentions(max_results=max_results)
