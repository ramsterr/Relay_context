"""
Retry policies with exponential backoff for async operations.

This module provides configurable retry strategies for handling transient failures
in LLM calls, embedding generation, Redis operations, and other external dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Set, Type
from functools import wraps

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"


@dataclass
class RetryPolicy:
    """
    Configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of retry attempts (including initial attempt)
        base_delay: Base delay in seconds between retries
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to prevent thundering herd
        retryable_exceptions: Set of exception types that should trigger retry
        strategy: Retry delay strategy to use
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    retryable_exceptions: Set[Type[Exception]] = field(default_factory=lambda: {
        ConnectionError,
        TimeoutError,
        OSError,
    })
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number."""
        if self.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay * (self.exponential_base ** attempt)
        elif self.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.base_delay * (attempt + 1)
        else:  # FIXED_DELAY
            delay = self.base_delay
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter if enabled
        if self.jitter:
            jitter_range = delay * self.jitter_factor
            delay += random.uniform(-jitter_range, jitter_range)
            delay = max(0, delay)  # Ensure non-negative
        
        return delay
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if an exception should be retried."""
        if attempt >= self.max_attempts:
            return False
        
        return any(
            isinstance(exception, exc_type) 
            for exc_type in self.retryable_exceptions
        )


# Default retry policies for common scenarios
DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    retryable_exceptions={ConnectionError, TimeoutError, OSError},
)

LLM_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=2.0,
    max_delay=120.0,
    retryable_exceptions={ConnectionError, TimeoutError, OSError},
)

REDIS_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=0.5,
    max_delay=10.0,
    retryable_exceptions={ConnectionError, TimeoutError, OSError},
)

EMBEDDING_RETRY_POLICY = RetryPolicy(
    max_attempts=4,
    base_delay=1.5,
    max_delay=60.0,
    retryable_exceptions={ConnectionError, TimeoutError, OSError},
)


def with_retry(policy: Optional[RetryPolicy] = None):
    """
    Decorator to add retry logic to async functions.
    
    Args:
        policy: RetryPolicy configuration. Uses DEFAULT_RETRY_POLICY if not provided.
    
    Returns:
        Decorated function with retry behavior.
    
    Example:
        @with_retry(LLM_RETRY_POLICY)
        async def call_llm(prompt: str) -> str:
            # ... LLM call that may fail
    """
    if policy is None:
        policy = DEFAULT_RETRY_POLICY
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(policy.max_attempts):
                try:
                    logger.debug(
                        f"Executing {func.__name__} (attempt {attempt + 1}/{policy.max_attempts})"
                    )
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    
                    if not policy.should_retry(e, attempt):
                        logger.error(
                            f"{func.__name__} failed with non-retryable error: {e}"
                        )
                        raise
                    
                    if attempt < policy.max_attempts - 1:
                        delay = policy.get_delay(attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}): {e}. "
                            f"Retrying in {delay:.2f}s"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {policy.max_attempts} attempts: {e}"
                        )
            
            # Should never reach here, but just in case
            raise last_exception  # type: ignore
        
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry operations with state tracking.
    
    Useful for manual retry logic outside of decorators.
    
    Example:
        async with RetryContext(policy=REDIS_RETRY_POLICY) as ctx:
            while ctx.should_continue():
                try:
                    result = await redis_operation()
                    break
                except Exception as e:
                    await ctx.handle_failure(e)
    """
    
    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or DEFAULT_RETRY_POLICY
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
        self.start_time: Optional[float] = None
    
    def __enter__(self) -> "RetryContext":
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def __aenter__(self) -> "RetryContext":
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def should_continue(self) -> bool:
        """Check if more retry attempts are available."""
        return self.attempt < self.policy.max_attempts
    
    async def handle_failure(self, exception: Exception) -> None:
        """
        Handle a failed attempt and wait before next retry.
        
        Raises:
            The exception if no more retries are available.
        """
        self.last_exception = exception
        self.attempt += 1
        
        if not self.policy.should_retry(exception, self.attempt):
            logger.error(
                f"Operation failed after {self.attempt} attempts: {exception}"
            )
            raise exception
        
        delay = self.policy.get_delay(self.attempt - 1)
        logger.warning(
            f"Attempt {self.attempt} failed: {exception}. Retrying in {delay:.2f}s"
        )
        await asyncio.sleep(delay)
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time since context started."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance.
    
    Prevents cascading failures by failing fast when a service is unhealthy.
    
    Attributes:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before testing recovery
        expected_exception: Exception type to count as failure
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: Type[Exception] = Exception,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._success_count = 0
    
    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit state."""
        # Check if we should transition from OPEN to HALF_OPEN
        if self._state == CircuitBreakerState.OPEN:
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._failure_count = 0
        return self._state
    
    def call(self, func: Callable) -> Callable:
        """
        Decorator to wrap a function with circuit breaker logic.
        
        Example:
            @circuit_breaker.call
            async def call_external_service():
                # ...
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.execute(func, *args, **kwargs)
        return wrapper
    
    async def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Raises:
            CircuitBreakerOpenError: If circuit is open and rejecting requests.
        """
        if self.state == CircuitBreakerState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN. Service unavailable."
            )
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self._success_count += 1
        
        if self._state == CircuitBreakerState.HALF_OPEN:
            logger.info(f"Circuit breaker '{self.name}' recovered, closing circuit")
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitBreakerState.OPEN:
                logger.warning(
                    f"Circuit breaker '{self.name}' OPENED after {self._failure_count} failures"
                )
                self._state = CircuitBreakerState.OPEN
    
    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
    
    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name}, state={self.state.value}, "
            f"failures={self._failure_count}/{self.failure_threshold})"
        )


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and rejecting requests."""
    pass


# Global circuit breaker registry for managing multiple breakers
class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    _instance: Optional["CircuitBreakerRegistry"] = None
    
    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers = {}
        return cls._instance
    
    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return self._breakers[name]
    
    def get_all_states(self) -> dict[str, CircuitBreakerState]:
        """Get states of all circuit breakers."""
        return {name: cb.state for name, cb in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for cb in self._breakers.values():
            cb.reset()


# Convenience functions for common patterns
async def retry_operation(
    operation: Callable,
    policy: Optional[RetryPolicy] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute an operation with retry logic.
    
    Alternative to using the decorator when you need dynamic retry.
    """
    decorated = with_retry(policy)(operation)
    return await decorated(*args, **kwargs)


def create_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Create and register a circuit breaker."""
    registry = CircuitBreakerRegistry()
    return registry.get_or_create(name, failure_threshold, recovery_timeout)
