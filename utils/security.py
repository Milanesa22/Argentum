"""
AURELIUS Security Module
Handles input sanitization, validation, and security measures.
"""

import re
import html
import bleach
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import hashlib
import secrets
import json

from ..logging_config import get_logger

logger = get_logger("SECURITY")

class SecurityValidator:
    """Security validation and sanitization utilities."""
    
    # Allowed HTML tags for social media content (very restrictive)
    ALLOWED_TAGS = ['b', 'i', 'em', 'strong', 'u']
    ALLOWED_ATTRIBUTES = {}
    
    # Dangerous patterns to detect
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript URLs
        r'on\w+\s*=',  # Event handlers
        r'<iframe[^>]*>.*?</iframe>',  # Iframes
        r'<object[^>]*>.*?</object>',  # Objects
        r'<embed[^>]*>.*?</embed>',  # Embeds
        r'<link[^>]*>',  # Link tags
        r'<meta[^>]*>',  # Meta tags
        r'<style[^>]*>.*?</style>',  # Style tags
        r'data:text/html',  # Data URLs
        r'vbscript:',  # VBScript
        r'expression\s*\(',  # CSS expressions
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)',
        r'(\b(OR|AND)\s+\d+\s*=\s*\d+)',
        r'(\b(OR|AND)\s+[\'"]?\w+[\'"]?\s*=\s*[\'"]?\w+[\'"]?)',
        r'(--|#|/\*|\*/)',
        r'(\bxp_\w+)',
        r'(\bsp_\w+)',
    ]
    
    @staticmethod
    def sanitize_text(text: str, max_length: Optional[int] = None) -> str:
        """
        Sanitize text input for social media posting.
        Removes dangerous HTML, scripts, and limits length.
        """
        if not isinstance(text, str):
            logger.warning(f"⚠️  Non-string input received for sanitization: {type(text)}")
            text = str(text)
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # HTML escape first
        text = html.escape(text)
        
        # Use bleach for additional sanitization
        text = bleach.clean(
            text,
            tags=SecurityValidator.ALLOWED_TAGS,
            attributes=SecurityValidator.ALLOWED_ATTRIBUTES,
            strip=True
        )
        
        # Remove dangerous patterns
        for pattern in SecurityValidator.DANGEROUS_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Limit length if specified
        if max_length and len(text) > max_length:
            text = text[:max_length-3] + "..."
            logger.info(f"📏 Text truncated to {max_length} characters")
        
        return text
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL for safety.
        Returns True if URL is safe to use.
        """
        if not isinstance(url, str):
            return False
        
        try:
            parsed = urlparse(url)
            
            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Only allow HTTP/HTTPS
            if parsed.scheme.lower() not in ['http', 'https']:
                logger.warning(f"⚠️  Invalid URL scheme: {parsed.scheme}")
                return False
            
            # Block localhost and private IPs in production
            if parsed.netloc.lower() in ['localhost', '127.0.0.1', '0.0.0.0']:
                logger.warning(f"⚠️  Localhost URL blocked: {url}")
                return False
            
            # Block private IP ranges
            if re.match(r'^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)', parsed.netloc):
                logger.warning(f"⚠️  Private IP URL blocked: {url}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ URL validation error: {e}")
            return False
    
    @staticmethod
    def detect_sql_injection(text: str) -> bool:
        """
        Detect potential SQL injection attempts.
        Returns True if suspicious patterns are found.
        """
        if not isinstance(text, str):
            return False
        
        text_upper = text.upper()
        
        for pattern in SecurityValidator.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                logger.warning(f"🚨 Potential SQL injection detected: {pattern}")
                return True
        
        return False
    
    @staticmethod
    def sanitize_json_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize JSON data recursively.
        Cleans all string values and validates structure.
        """
        if not isinstance(data, dict):
            logger.warning(f"⚠️  Non-dict data received for JSON sanitization: {type(data)}")
            return {}
        
        sanitized = {}
        
        for key, value in data.items():
            # Sanitize key
            clean_key = SecurityValidator.sanitize_text(str(key), max_length=100)
            
            if isinstance(value, str):
                # Sanitize string values
                sanitized[clean_key] = SecurityValidator.sanitize_text(value, max_length=10000)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[clean_key] = SecurityValidator.sanitize_json_data(value)
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[clean_key] = SecurityValidator.sanitize_list_data(value)
            elif isinstance(value, (int, float, bool)) or value is None:
                # Keep safe primitive types
                sanitized[clean_key] = value
            else:
                # Convert other types to string and sanitize
                sanitized[clean_key] = SecurityValidator.sanitize_text(str(value), max_length=1000)
        
        return sanitized
    
    @staticmethod
    def sanitize_list_data(data: List[Any]) -> List[Any]:
        """Sanitize list data recursively."""
        if not isinstance(data, list):
            return []
        
        sanitized = []
        
        for item in data:
            if isinstance(item, str):
                sanitized.append(SecurityValidator.sanitize_text(item, max_length=1000))
            elif isinstance(item, dict):
                sanitized.append(SecurityValidator.sanitize_json_data(item))
            elif isinstance(item, list):
                sanitized.append(SecurityValidator.sanitize_list_data(item))
            elif isinstance(item, (int, float, bool)) or item is None:
                sanitized.append(item)
            else:
                sanitized.append(SecurityValidator.sanitize_text(str(item), max_length=1000))
        
        return sanitized
    
    @staticmethod
    def validate_api_key(api_key: str, min_length: int = 10) -> bool:
        """
        Validate API key format.
        Returns True if key appears to be valid format.
        """
        if not isinstance(api_key, str):
            return False
        
        # Remove whitespace
        api_key = api_key.strip()
        
        # Check minimum length
        if len(api_key) < min_length:
            return False
        
        # Check for suspicious patterns
        if SecurityValidator.detect_sql_injection(api_key):
            return False
        
        # Should not contain HTML
        if '<' in api_key or '>' in api_key:
            return False
        
        return True
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_sensitive_data(data: str, salt: Optional[str] = None) -> str:
        """
        Hash sensitive data with optional salt.
        Returns SHA-256 hash.
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        combined = f"{data}{salt}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @staticmethod
    def validate_social_content(content: str, platform: str) -> Dict[str, Any]:
        """
        Validate and sanitize content for social media platforms.
        Returns a dictionary with validation results.
        """
        if not isinstance(content, str):
            logger.warning(f"⚠️  Non-string content received for validation: {type(content)}")
            content = str(content)
        
        # Initialize result structure
        result = {
            'valid': True,
            'content': content,
            'warnings': [],
            'errors': []
        }
        
        # Platform-specific limits
        limits = {
            'twitter': 280,
            'mastodon': 500,
            'discord': 2000
        }
        
        platform_lower = platform.lower()
        max_length = limits.get(platform_lower, 1000)
        
        # Sanitize content
        sanitized_content = SecurityValidator.sanitize_text(content, max_length)
        result['content'] = sanitized_content

        # SOLO para Webhooks y entradas de usuario REAL (no IA/autopost)
        if platform_lower not in ['twitter', 'mastodon', 'discord']:
            # Check for dangerous patterns
            for pattern in SecurityValidator.DANGEROUS_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    result['errors'].append(f"Dangerous pattern detected: {pattern}")
                    result['valid'] = False

            # Check for SQL injection
            if SecurityValidator.detect_sql_injection(content):
                result['errors'].append("Potential SQL injection detected")
                result['valid'] = False

        # Length validation
        if len(sanitized_content) != len(content):
            result['warnings'].append("Content was sanitized and may have been modified")
        
        if len(sanitized_content) > max_length:
            result['warnings'].append(f"Content exceeds {platform} limit of {max_length} characters")
        
        # Empty content check
        if not sanitized_content.strip():
            result['errors'].append("Content is empty after sanitization")
            result['valid'] = False
        
        return result
    
    @staticmethod
    def sanitize_webhook_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize webhook data from external sources.
        Extra security for payment and social media webhooks.
        """
        if not isinstance(data, dict):
            logger.error("❌ Invalid webhook data format")
            return {}
        
        # Log incoming webhook for security monitoring
        logger.info(f"🔒 Processing webhook data with {len(data)} fields")
        
        # Sanitize the data
        sanitized = SecurityValidator.sanitize_json_data(data)
        
        # Additional webhook-specific validation
        for key, value in sanitized.items():
            if isinstance(value, str):
                # Check for suspicious webhook content
                if any(pattern in value.lower() for pattern in ['<script', 'javascript:', 'data:text/html']):
                    logger.warning(f"🚨 Suspicious webhook content in field '{key}': {value[:100]}...")
                    sanitized[key] = SecurityValidator.sanitize_text(value)
        
        return sanitized

# Global security validator instance
security = SecurityValidator()

def sanitize_for_social(content: str, platform: str) -> str:
    """Quick function to sanitize content for social media posting."""
    validation = security.validate_social_content(content, platform)
    if not validation['valid']:
        logger.error(f"❌ Content validation failed for {platform}: {validation['errors']}")
        return ""
    
    if validation['warnings']:
        for warning in validation['warnings']:
            logger.warning(f"⚠️  Content warning for {platform}: {warning}")
    
    return validation['content']

def validate_and_sanitize_input(data: Any, data_type: str = "general") -> Any:
    """
    General purpose input validation and sanitization.
    Returns sanitized data or raises exception for invalid input.
    """
    try:
        if isinstance(data, str):
            return security.sanitize_text(data)
        elif isinstance(data, dict):
            return security.sanitize_json_data(data)
        elif isinstance(data, list):
            return security.sanitize_list_data(data)
        else:
            return data
    except Exception as e:
        logger.error(f"❌ Input sanitization failed for {data_type}: {e}")
        raise ValueError(f"Invalid input data for {data_type}")
# --- Helpers sociales para cortar y derivar a Discord ---

DISCORD_CONTACT_MSG = (
    "\n\n👉 Para obtener el workflow completo, escribime por privado a Discord: @AureliusChat"
)

def add_discord_contact(content: str, platform: str) -> str:
    """Agrega llamada a contactarse por Discord si la plataforma no permite DMs."""
    if platform.lower() not in ["discord"]:
        if DISCORD_CONTACT_MSG.strip().lower() not in content.lower():
            content = content.rstrip() + DISCORD_CONTACT_MSG
    return content

def truncate_for_discord(content: str) -> str:
    """Corta el contenido y lo remata invitando a Discord si es muy largo."""
    max_length = 2000
    if len(content) > max_length:
        allowed = max_length - len(DISCORD_CONTACT_MSG)
        content = content[:allowed-3] + "..." + DISCORD_CONTACT_MSG
    return content

def sanitize_and_prepare_content(content: str, platform: str) -> str:
    """Sanitiza, corta y agrega invitación a Discord si hace falta."""
    sanitized = sanitize_for_social(content, platform)
    # Si no es Discord y no permite DM, invita igual (ajustá si querés sólo para workflows)
    if platform.lower() in ["twitter", "mastodon"]:
        sanitized = add_discord_contact(sanitized, platform)
    if platform.lower() == "discord":
        sanitized = truncate_for_discord(sanitized)
    return sanitized
# --- Fin de helpers sociales ---