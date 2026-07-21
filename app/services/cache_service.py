import logging
import math
import time

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


KEY_PREFIX_RATELIMIT = "app:ratelimit:"
logger = logging.getLogger(__name__)

async def check_and_increment_rate_limit(
    redis: Redis,
    user_email: str,
) -> tuple[bool, int]:
    settings = get_settings()

    unix_minute = math.floor(time.time() / 60)
    rate_key = f"{KEY_PREFIX_RATELIMIT}{user_email}:{unix_minute}"

    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(rate_key)
            # EXPIRE is only applied on first INCR (result==1) but we set it
            # every time as a safety net (idempotent if already set).
            pipe.expire(rate_key, 60)
            results = await pipe.execute()
        
        current_count = results[0]

        if current_count > settings.rate_limit_max:
            # Calculate seconds until the next 60s window starts.
            seconds_elapsed_in_window = int(time.time() % 60)
            retry_after = 60 - seconds_elapsed_in_window
            logger.warning(
                "Rate limit exceeded for service '%s': %d/%d requests in current window.",
                user_email,
                current_count,
                settings.rate_limit_max,
            )
            return False, retry_after
        
        return True, 0
    
    except RedisError as exc:
        # Fail-open: don't block ingestion on Redis unavailability.
        logger.warning(
            "Redis error during rate limit check for service '%s' — "
            "allowing request through (fail-open): %s",
            user_email,
            exc,
        )
        return True, 0