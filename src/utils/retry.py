"""
Retry decorator with exponential backoff for transient failures.
"""

import functools
import time
import logging
from typing import Callable, TypeVar, Any, Type, Tuple

from .logger import get_logger

T = TypeVar("T")


class MaxRetriesExceeded(Exception):
    """Raised when max retries are exceeded."""
    
    def __init__(self, operation: str, attempts: int, last_error: Exception):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Operation '{operation}' failed after {attempts} attempts. "
            f"Last error: {last_error}"
        )


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    operation_name: str = None,
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exception types to catch and retry
        operation_name: Name for logging (defaults to function name)
        
    Returns:
        Decorated function with retry logic
        
    Example:
        @retry_with_backoff(max_retries=3, base_delay=2.0)
        def flaky_network_call():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            logger = get_logger()
            op_name = operation_name or func.__name__
            
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"[error]✗[/error] {op_name} failed after {attempt} attempts: {e}"
                        )
                        raise MaxRetriesExceeded(op_name, attempt, e)
                    
                    # Calculate backoff delay
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    logger.warning(
                        f"[warning]⚠[/warning] {op_name} attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
            
            # Should never reach here, but just in case
            raise MaxRetriesExceeded(op_name, max_retries, last_exception)
        
        return wrapper
    return decorator


def retry_async_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    operation_name: str = None,
) -> Callable:
    """
    Async version of retry_with_backoff for asyncio functions.
    """
    import asyncio
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            logger = get_logger()
            op_name = operation_name or func.__name__
            
            last_exception = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"[error]✗[/error] {op_name} failed after {attempt} attempts: {e}"
                        )
                        raise MaxRetriesExceeded(op_name, attempt, e)
                    
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    logger.warning(
                        f"[warning]⚠[/warning] {op_name} attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    await asyncio.sleep(delay)
            
            raise MaxRetriesExceeded(op_name, max_retries, last_exception)
        
        return wrapper
    return decorator
