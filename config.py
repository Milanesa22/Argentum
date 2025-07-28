"""
AURELIUS Configuration Module
Handles all environment variables, API keys validation, and system settings.
"""

import os
from typing import Optional, Dict, Any
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import validator, Field
from dotenv import load_dotenv
import sys

# Load environment variables from .env file
load_dotenv()

# Precios
WORKFLOW_PRICE_USD = 5  # Cambiá a lo que quieras cobrar (por ejemplo, 5 USD)
COTIZACION_USD_ARS = 1400  # Cambiá por la cotización real, si querés mostrar en ARS
WORKFLOW_PRICE_ARS = int(WORKFLOW_PRICE_USD * COTIZACION_USD_ARS)
PAY_LINK = "https://paypal.me/streetfits"  # Tu link real de pago PayPal


class AureliusConfig(BaseSettings):
    """Main configuration class with validation for all required API keys and settings."""
    
    # OpenAI/OpenRouter Configuration
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key for GPT-4/GPT-4o")
    OPENROUTER_API_KEY: Optional[str] = Field(None, description="OpenRouter API key (alternative to OpenAI)")
    OPENAI_MODEL: str = Field(default="openai/gpt-4o", description="Model to use for AI generation")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1", description="API base URL")
    
    # Social Media API Keys
    TWITTER_API_KEY: str = Field(..., description="Twitter API Key")
    TWITTER_API_SECRET: str = Field(..., description="Twitter API Secret")
    TWITTER_ACCESS_TOKEN: str = Field(..., description="Twitter Access Token")
    TWITTER_ACCESS_TOKEN_SECRET: str = Field(..., description="Twitter Access Token Secret")
    TWITTER_BEARER_TOKEN: str = Field(..., description="Twitter Bearer Token")
    
    MASTODON_ACCESS_TOKEN: str = Field(..., description="Mastodon Access Token")
    MASTODON_API_BASE_URL: str = Field(..., description="Mastodon instance URL (e.g., https://mastodon.social)")
    
    DISCORD_BOT_TOKEN: str = Field(..., description="Discord Bot Token")
    DISCORD_WEBHOOK_URL: Optional[str] = Field(None, description="Discord Webhook URL for posting")
    DISCORD_CHANNEL_ID: Optional[str] = Field(None, description="Discord Channel ID for posting")
    
    # PayPal Configuration
    PAYPAL_CLIENT_ID: str = Field(..., description="PayPal Client ID")
    PAYPAL_CLIENT_SECRET: str = Field(..., description="PayPal Client Secret")
    PAYPAL_MODE: str = Field(default="sandbox", description="PayPal mode: sandbox or live")
    PAYPAL_WEBHOOK_ID: Optional[str] = Field(None, description="PayPal Webhook ID for payment notifications")
    
    # Redis Configuration
    REDIS_URL: Optional[str] = Field(default="redis://default:48DL3xbcWQ7nPsaVjNUAOnxMQ5E1xSaJ@redis-19257.c1.us-central1-2.gce.redns.redis-cloud.com:19257/0", description="Redis connection URL")
    REDIS_PASSWORD: Optional[str] = Field(None, description="Redis password if required")
    REDIS_DB: int = Field(default=0, description="Redis database number")
    
    # Rate Limiting Configuration
    TWITTER_DAILY_POST_LIMIT: int = Field(default=50, description="Daily Twitter post limit")
    TWITTER_HOURLY_POST_LIMIT: int = Field(default=5, description="Hourly Twitter post limit")
    MASTODON_DAILY_POST_LIMIT: int = Field(default=100, description="Daily Mastodon post limit")
    MASTODON_HOURLY_POST_LIMIT: int = Field(default=10, description="Hourly Mastodon post limit")
    DISCORD_DAILY_POST_LIMIT: int = Field(default=200, description="Daily Discord post limit")
    DISCORD_HOURLY_POST_LIMIT: int = Field(default=20, description="Hourly Discord post limit")
    
    # System Configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE_PATH: str = Field(default="logs/aurelius.log", description="Log file path")
    DATA_STORAGE_PATH: str = Field(default="data/", description="Local storage path for fallback")
    
    # AI Prompt Configuration
    DEFAULT_SYSTEM_PROMPT: str = Field(
        default="You are AURELIUS, an AI assistant for automated business management and sales. Generate engaging, professional content for social media and sales communications.",
        description="Default system prompt for AI interactions"
    )
    SALES_PROMPT_TEMPLATE: str = Field(
        default="Generate a compelling sales message for {product} targeting {audience}. Keep it professional and engaging.",
        description="Template for sales content generation"
    )
    
    # Webhook and Server Configuration
    WEBHOOK_PORT: int = Field(default=8080, description="Port for webhook server")
    WEBHOOK_HOST: str = Field(default="0.0.0.0", description="Host for webhook server")
    
    @validator('PAYPAL_MODE')
    def validate_paypal_mode(cls, v):
        if v not in ['sandbox', 'live']:
            raise ValueError('PAYPAL_MODE must be either "sandbox" or "live"')
        return v
    
    @validator('LOG_LEVEL')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'LOG_LEVEL must be one of: {", ".join(valid_levels)}')
        return v.upper()
    
    @validator('OPENAI_MODEL')
    def validate_openai_model(cls, v):
        valid_models = [
            'openai/gpt-4o', 'openai/gpt-4', 'openai/gpt-4-turbo',
            'anthropic/claude-3-sonnet', 'anthropic/claude-3-haiku'
        ]
        if v not in valid_models:
            print(f"Warning: Model '{v}' not in recommended list. Proceeding anyway.")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True

def validate_required_keys(config: AureliusConfig) -> Dict[str, Any]:
    """
    Validate that all required API keys are present and provide detailed error messages.
    Returns a dictionary of validation results.
    """
    validation_results = {
        'valid': True,
        'errors': [],
        'warnings': []
    }
    
    # Required keys validation
    required_keys = [
        ('OPENAI_API_KEY', 'OpenAI API key is required for AI functionality'),
        ('TWITTER_API_KEY', 'Twitter API key is required for Twitter integration'),
        ('TWITTER_API_SECRET', 'Twitter API secret is required for Twitter integration'),
        ('TWITTER_ACCESS_TOKEN', 'Twitter access token is required for Twitter integration'),
        ('TWITTER_ACCESS_TOKEN_SECRET', 'Twitter access token secret is required for Twitter integration'),
        ('TWITTER_BEARER_TOKEN', 'Twitter bearer token is required for Twitter integration'),
        ('MASTODON_ACCESS_TOKEN', 'Mastodon access token is required for Mastodon integration'),
        ('MASTODON_API_BASE_URL', 'Mastodon API base URL is required for Mastodon integration'),
        ('DISCORD_BOT_TOKEN', 'Discord bot token is required for Discord integration'),
        ('PAYPAL_CLIENT_ID', 'PayPal client ID is required for payment processing'),
        ('PAYPAL_CLIENT_SECRET', 'PayPal client secret is required for payment processing'),
    ]
    
    for key, error_msg in required_keys:
        value = getattr(config, key, None)
        if not value or value.strip() == '':
            validation_results['errors'].append(f"❌ {error_msg}")
            validation_results['valid'] = False
    
    # Optional but recommended keys
    optional_keys = [
        ('DISCORD_WEBHOOK_URL', 'Discord webhook URL is recommended for posting to channels'),
        ('PAYPAL_WEBHOOK_ID', 'PayPal webhook ID is recommended for payment notifications'),
        ('REDIS_URL', 'Redis URL is recommended for data persistence'),
    ]
    
    for key, warning_msg in optional_keys:
        value = getattr(config, key, None)
        if not value or value.strip() == '':
            validation_results['warnings'].append(f"⚠️  {warning_msg}")
    
    return validation_results

def create_directories(config: AureliusConfig) -> None:
    """Create necessary directories for logs and data storage."""
    try:
        # Create log directory
        log_dir = Path(config.LOG_FILE_PATH).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create data storage directory
        data_dir = Path(config.DATA_STORAGE_PATH)
        data_dir.mkdir(parents=True, exist_ok=True)
        
    except Exception as e:
        print(f"Warning: Could not create directories: {e}")

def load_config() -> AureliusConfig:
    """
    Load and validate configuration.
    Exits the application if critical validation fails.
    """
    try:
        config = AureliusConfig()
        
        # Create necessary directories
        create_directories(config)
        
        # Validate configuration
        validation = validate_required_keys(config)
        
        # Print validation results
        if validation['errors']:
            print("\n🚨 CONFIGURATION ERRORS:")
            for error in validation['errors']:
                print(f"  {error}")
            print("\n💡 Please check your .env file or environment variables.")
            print("   Create a .env file in the aurelius directory with all required keys.")
            sys.exit(1)
        
        if validation['warnings']:
            print("\n⚠️  CONFIGURATION WARNINGS:")
            for warning in validation['warnings']:
                print(f"  {warning}")
            print()
        
        print("✅ Configuration loaded successfully!")
        return config
        
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        print("💡 Please check your .env file format and ensure all required variables are set.")
        sys.exit(1)

# Global configuration instance
config = load_config()
