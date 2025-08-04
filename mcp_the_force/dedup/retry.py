"""SQLite retry utilities for handling database lock contention.

This module provides comprehensive retry logic for SQLite operations, designed to handle
transient database errors like locks and busy states with exponential backoff.
"""

import asyncio
import sqlite3
import time
import random
import logging
from typing import Callable, Any, Optional, Type
from functools import wraps

from .errors import CacheTransactionError

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 2.0,
        backoff_multiplier: float = 2.0,
        jitter_factor: float = 0.1,
    ):
        """Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds for first retry
            max_delay: Maximum delay in seconds between retries
            backoff_multiplier: Multiplier for exponential backoff
            jitter_factor: Random jitter factor (0.0 to 1.0) to prevent thundering herd
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter_factor = jitter_factor


def is_retryable_sqlite_error(error: sqlite3.Error) -> bool:
    """Determine if a SQLite error is retryable.

    Args:
        error: The SQLite error to check

    Returns:
        True if the error indicates a transient condition that can be retried
    """
    error_msg = str(error).lower()

    # Retryable errors - transient lock contention
    retryable_patterns = [
        "database is locked",
        "database is busy",
        "cannot start a transaction within a transaction",  # Sometimes indicates lock contention
        "disk i/o error",  # May be transient
    ]

    return any(pattern in error_msg for pattern in retryable_patterns)


def is_non_retryable_sqlite_error(error: sqlite3.Error) -> bool:
    """Determine if a SQLite error should not be retried.

    Args:
        error: The SQLite error to check

    Returns:
        True if the error indicates a persistent condition that won't be fixed by retrying
    """
    error_msg = str(error).lower()

    # Non-retryable errors - these indicate logic errors or persistent problems
    non_retryable_patterns = [
        "constraint failed",
        "unique constraint failed",  # This is expected behavior in atomic operations
        "foreign key constraint failed",
        "no such table",
        "no such column",
        "syntax error",
        "database disk image is malformed",
        "not a database",
        "file is not a database",
    ]

    return any(pattern in error_msg for pattern in non_retryable_patterns)


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for exponential backoff with jitter.

    Args:
        attempt: Current attempt number (0-based)
        config: Retry configuration

    Returns:
        Delay in seconds for this attempt
    """
    # Exponential backoff: base_delay * (multiplier ^ attempt)
    delay = config.base_delay * (config.backoff_multiplier**attempt)

    # Cap at max_delay
    delay = min(delay, config.max_delay)

    # Add jitter to prevent thundering herd
    if config.jitter_factor > 0:
        jitter = delay * config.jitter_factor * random.random()
        delay += jitter

    return delay


def retry_sqlite_operation(
    config: Optional[RetryConfig] = None,
    wrap_exception: Type[Exception] = CacheTransactionError,
    operation_description: str = "SQLite operation",
):
    """Decorator for retrying SQLite operations with exponential backoff.

    This decorator handles transient SQLite errors like database locks by retrying
    the operation with exponential backoff. Non-retryable errors are re-raised immediately.

    Args:
        config: Retry configuration. If None, uses default config.
        wrap_exception: Exception type to wrap SQLite errors in
        operation_description: Description for error messages

    Usage:
        @retry_sqlite_operation(config=RetryConfig(max_attempts=5))
        def my_database_operation(self):
            # Database operation that might fail due to locks
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error: Optional[sqlite3.Error] = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except sqlite3.Error as e:
                    last_error = e

                    # Check if this error should be retried
                    if is_non_retryable_sqlite_error(e):
                        logger.debug(
                            f"Non-retryable SQLite error in {operation_description}: {e}"
                        )
                        # Wrap and re-raise immediately for non-retryable errors
                        raise wrap_exception(
                            f"{operation_description} failed: {e}"
                        ) from e

                    if not is_retryable_sqlite_error(e):
                        logger.debug(
                            f"Unknown SQLite error in {operation_description}: {e}"
                        )
                        # Unknown errors are treated as non-retryable for safety
                        raise wrap_exception(
                            f"{operation_description} failed: {e}"
                        ) from e

                    # This is a retryable error
                    if attempt < config.max_attempts - 1:
                        delay = calculate_delay(attempt, config)
                        logger.warning(
                            f"{operation_description} failed (attempt {attempt + 1}/{config.max_attempts}): {e}. "
                            f"Retrying in {delay:.3f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{operation_description} failed after {config.max_attempts} attempts: {e}"
                        )

                except Exception as e:
                    # Non-SQLite exceptions are not retried
                    logger.error(f"Non-SQLite error in {operation_description}: {e}")
                    raise

            # If we get here, all retries were exhausted
            if last_error:
                raise wrap_exception(
                    f"{operation_description} failed after {config.max_attempts} retry attempts: {last_error}"
                ) from last_error
            else:
                raise wrap_exception(
                    f"{operation_description} failed after {config.max_attempts} attempts"
                )

        return wrapper

    return decorator


def retry_sqlite_operation_async(
    config: Optional[RetryConfig] = None,
    wrap_exception: Type[Exception] = CacheTransactionError,
    operation_description: str = "SQLite operation",
):
    """Async decorator for retrying SQLite operations with exponential backoff.

    Similar to retry_sqlite_operation but uses asyncio.sleep for non-blocking delays.

    Args:
        config: Retry configuration. If None, uses default config.
        wrap_exception: Exception type to wrap SQLite errors in
        operation_description: Description for error messages

    Usage:
        @retry_sqlite_operation_async(config=RetryConfig(max_attempts=5))
        async def my_async_database_operation(self):
            # Database operation that might fail due to locks
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_error: Optional[sqlite3.Error] = None

            for attempt in range(config.max_attempts):
                try:
                    # Check if the function is async
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)

                except sqlite3.Error as e:
                    last_error = e

                    # Check if this error should be retried
                    if is_non_retryable_sqlite_error(e):
                        logger.debug(
                            f"Non-retryable SQLite error in {operation_description}: {e}"
                        )
                        # Wrap and re-raise immediately for non-retryable errors
                        raise wrap_exception(
                            f"{operation_description} failed: {e}"
                        ) from e

                    if not is_retryable_sqlite_error(e):
                        logger.debug(
                            f"Unknown SQLite error in {operation_description}: {e}"
                        )
                        # Unknown errors are treated as non-retryable for safety
                        raise wrap_exception(
                            f"{operation_description} failed: {e}"
                        ) from e

                    # This is a retryable error
                    if attempt < config.max_attempts - 1:
                        delay = calculate_delay(attempt, config)
                        logger.warning(
                            f"{operation_description} failed (attempt {attempt + 1}/{config.max_attempts}): {e}. "
                            f"Retrying in {delay:.3f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{operation_description} failed after {config.max_attempts} attempts: {e}"
                        )

                except Exception as e:
                    # Non-SQLite exceptions are not retried
                    logger.error(f"Non-SQLite error in {operation_description}: {e}")
                    raise

            # If we get here, all retries were exhausted
            if last_error:
                raise wrap_exception(
                    f"{operation_description} failed after {config.max_attempts} retry attempts: {last_error}"
                ) from last_error
            else:
                raise wrap_exception(
                    f"{operation_description} failed after {config.max_attempts} attempts"
                )

        return wrapper

    return decorator


# Default retry configurations for different operations
DEFAULT_RETRY_CONFIG = RetryConfig(max_attempts=3, base_delay=0.1, max_delay=2.0)
ATOMIC_OPERATION_RETRY_CONFIG = RetryConfig(
    max_attempts=5, base_delay=0.05, max_delay=1.0
)
READ_OPERATION_RETRY_CONFIG = RetryConfig(
    max_attempts=2, base_delay=0.05, max_delay=0.5
)
