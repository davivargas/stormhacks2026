from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


async def retry_async(operation: Callable[[], Awaitable[T]], attempts: int) -> T:
    """Retry a bounded provider operation without exposing provider errors."""

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as error:  # Provider SDKs do not share one exception base class.
            last_error = error
            if attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (2**attempt))
    assert last_error is not None
    raise last_error
