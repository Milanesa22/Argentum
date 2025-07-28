"""
AURELIUS Logging Configuration
Centralized logging setup using loguru for better async support and formatting.
"""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional
import asyncio

class AureliusLogger:
    """Centralized logger configuration for AURELIUS system."""
    
    def __init__(self, log_level: str = "INFO", log_file_path: str = "logs/aurelius.log"):
        self.log_level = log_level.upper()
        self.log_file_path = log_file_path
        self._configured = False
    
    def configure(self) -> None:
        """Configure loguru logger with file and console outputs."""
        if self._configured:
            return
        
        # Remove default logger
        logger.remove()
        
        # Create log directory if it doesn't exist
        log_dir = Path(self.log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Console logger with colors and formatting
        logger.add(
            sys.stdout,
            level=self.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level>",
            colorize=True,
            backtrace=True,
            diagnose=True
        )
        
        # File logger with rotation
        logger.add(
            self.log_file_path,
            level=self.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            backtrace=True,
            diagnose=True
        )
        
        # Error file logger
        error_log_path = str(Path(self.log_file_path).parent / "errors.log")
        logger.add(
            error_log_path,
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="5 MB",
            retention="60 days",
            compression="zip",
            backtrace=True,
            diagnose=True
        )
        
        self._configured = True
        logger.info("🚀 AURELIUS logging system initialized")
    
    def get_logger(self, name: Optional[str] = None):
        """Get a logger instance with optional name binding."""
        if not self._configured:
            self.configure()
        
        if name:
            return logger.bind(name=name)
        return logger

# Global logger instance
aurelius_logger = AureliusLogger()

def get_logger(name: Optional[str] = None):
    """Get the global AURELIUS logger instance."""
    return aurelius_logger.get_logger(name)

def log_api_call(service: str, endpoint: str, method: str = "GET", status: Optional[int] = None, error: Optional[str] = None):
    """Log API calls with standardized format."""
    logger_instance = get_logger("API")
    
    if error:
        logger_instance.error(f"❌ {service} API call failed | {method} {endpoint} | Error: {error}")
    elif status:
        if 200 <= status < 300:
            logger_instance.info(f"✅ {service} API call successful | {method} {endpoint} | Status: {status}")
        else:
            logger_instance.warning(f"⚠️  {service} API call warning | {method} {endpoint} | Status: {status}")
    else:
        logger_instance.info(f"📡 {service} API call initiated | {method} {endpoint}")

def log_rate_limit(service: str, limit_type: str, current: int, maximum: int):
    """Log rate limit status."""
    logger_instance = get_logger("RATE_LIMIT")
    
    percentage = (current / maximum) * 100 if maximum > 0 else 0
    
    if percentage >= 90:
        logger_instance.warning(f"🚨 {service} {limit_type} rate limit critical | {current}/{maximum} ({percentage:.1f}%)")
    elif percentage >= 75:
        logger_instance.warning(f"⚠️  {service} {limit_type} rate limit high | {current}/{maximum} ({percentage:.1f}%)")
    else:
        logger_instance.info(f"📊 {service} {limit_type} rate limit | {current}/{maximum} ({percentage:.1f}%)")

def log_payment_event(event_type: str, amount: Optional[float] = None, currency: str = "USD", transaction_id: Optional[str] = None, error: Optional[str] = None):
    """Log payment-related events."""
    logger_instance = get_logger("PAYMENTS")
    
    if error:
        logger_instance.error(f"💳❌ Payment {event_type} failed | {transaction_id or 'N/A'} | Error: {error}")
    else:
        amount_str = f"{amount} {currency}" if amount else "N/A"
        logger_instance.info(f"💳✅ Payment {event_type} | {transaction_id or 'N/A'} | Amount: {amount_str}")

def log_social_activity(platform: str, activity_type: str, content_preview: Optional[str] = None, success: bool = True, error: Optional[str] = None):
    """Log social media activities."""
    logger_instance = get_logger("SOCIAL")
    
    preview = f" | Preview: {content_preview[:50]}..." if content_preview else ""
    
    if not success and error:
        logger_instance.error(f"📱❌ {platform} {activity_type} failed{preview} | Error: {error}")
    else:
        logger_instance.info(f"📱✅ {platform} {activity_type} successful{preview}")

def log_ai_interaction(prompt_type: str, model: str, tokens_used: Optional[int] = None, success: bool = True, error: Optional[str] = None):
    """Log AI interactions."""
    logger_instance = get_logger("AI")
    
    tokens_str = f" | Tokens: {tokens_used}" if tokens_used else ""
    
    if not success and error:
        logger_instance.error(f"🤖❌ AI {prompt_type} failed | Model: {model}{tokens_str} | Error: {error}")
    else:
        logger_instance.info(f"🤖✅ AI {prompt_type} successful | Model: {model}{tokens_str}")

def log_data_operation(operation: str, data_type: str, count: Optional[int] = None, success: bool = True, error: Optional[str] = None):
    """Log data operations (Redis, local storage)."""
    logger_instance = get_logger("DATA")
    
    count_str = f" | Count: {count}" if count else ""
    
    if not success and error:
        logger_instance.error(f"💾❌ Data {operation} failed | Type: {data_type}{count_str} | Error: {error}")
    else:
        logger_instance.info(f"💾✅ Data {operation} successful | Type: {data_type}{count_str}")

async def log_async_task_start(task_name: str, task_id: Optional[str] = None):
    """Log the start of an async task."""
    logger_instance = get_logger("ASYNC")
    task_id_str = f" | ID: {task_id}" if task_id else ""
    logger_instance.info(f"⚡ Async task started | {task_name}{task_id_str}")

async def log_async_task_complete(task_name: str, task_id: Optional[str] = None, duration: Optional[float] = None, success: bool = True, error: Optional[str] = None):
    """Log the completion of an async task."""
    logger_instance = get_logger("ASYNC")
    task_id_str = f" | ID: {task_id}" if task_id else ""
    duration_str = f" | Duration: {duration:.2f}s" if duration else ""
    
    if not success and error:
        logger_instance.error(f"⚡❌ Async task failed | {task_name}{task_id_str}{duration_str} | Error: {error}")
    else:
        logger_instance.info(f"⚡✅ Async task completed | {task_name}{task_id_str}{duration_str}")

def log_system_startup():
    """Log system startup information."""
    logger_instance = get_logger("SYSTEM")
    logger_instance.info("🚀 AURELIUS system starting up...")
    logger_instance.info(f"🐍 Python version: {sys.version}")
    logger_instance.info(f"⚡ Asyncio event loop policy: {asyncio.get_event_loop_policy().__class__.__name__}")

def log_system_shutdown():
    """Log system shutdown information."""
    logger_instance = get_logger("SYSTEM")
    logger_instance.info("🛑 AURELIUS system shutting down...")

def log_configuration_loaded(config_items: int, warnings: int = 0, errors: int = 0):
    """Log configuration loading results."""
    logger_instance = get_logger("CONFIG")
    
    if errors > 0:
        logger_instance.error(f"⚙️❌ Configuration loaded with {errors} errors and {warnings} warnings | Items: {config_items}")
    elif warnings > 0:
        logger_instance.warning(f"⚙️⚠️  Configuration loaded with {warnings} warnings | Items: {config_items}")
    else:
        logger_instance.info(f"⚙️✅ Configuration loaded successfully | Items: {config_items}")
