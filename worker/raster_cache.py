"""Bounded measurement memoization without retaining raw raster keys."""
from collections import OrderedDict, namedtuple
from functools import wraps
from hashlib import sha256

CacheInfo = namedtuple('CacheInfo', 'hits misses maxsize currsize')


def _key(value):
    if isinstance(value, bytes):
        return (bytes, len(value), sha256(value).digest())
    if isinstance(value, tuple):
        return tuple(_key(item) for item in value)
    return value


def raster_cache(maxsize=128):
    """Cache small measurements by every input pixel, never the raster itself.

    SHA-256 keys retain byte length and all nonpixel parameters. Values must be
    measurement records, not PIL images or arrays. Each process owns its cache.
    """
    def decorate(function):
        cache = OrderedDict()
        hits = misses = 0

        @wraps(function)
        def wrapped(*args, **kwargs):
            nonlocal hits, misses
            key = (_key(args), tuple((k, _key(v)) for k, v in sorted(kwargs.items())))
            if key in cache:
                hits += 1
                cache.move_to_end(key)
                return cache[key]
            misses += 1
            result = function(*args, **kwargs)
            cache[key] = result
            if len(cache) > maxsize:
                cache.popitem(last=False)
            return result

        def clear():
            nonlocal hits, misses
            cache.clear()
            hits = misses = 0

        wrapped.cache_clear = clear
        wrapped.cache_info = lambda: CacheInfo(hits, misses, maxsize, len(cache))
        return wrapped
    return decorate
