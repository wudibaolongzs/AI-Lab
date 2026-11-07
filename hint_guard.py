"""Process-local cloud budget, bounded cache, and fail-fast admission.

Only digests and validated hint metadata are retained; no credentials or code.
"""
from collections import OrderedDict, deque
import hashlib
import json
import threading
import time


def cache_key(provider, model, endpoint, credential, exercise, evidence, level):
    digest = lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest(json.dumps([provider, model, digest(endpoint), digest(credential),
                              exercise, evidence, level], sort_keys=True, ensure_ascii=False))


class HintGuard:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.active = set()
        self.calls = deque()
        self.failures = 0
        self.open_until = None
        self.probe = False

    def begin(self, key):
        with self.lock:
            now = self.clock()
            for old in [k for k, (expiry, _) in self.cache.items() if expiry <= now]:
                del self.cache[old]
            if key in self.cache:
                self.cache.move_to_end(key)
                return "cached", dict(self.cache[key][1])
            if key in self.active or len(self.active) >= 2:
                return "busy", None
            if self.open_until is not None and (now < self.open_until or self.probe):
                return "circuit_open", None
            while self.calls and self.calls[0] <= now - 60:
                self.calls.popleft()
            if len(self.calls) >= 6:
                return "rate_limited", None
            if self.open_until is not None:
                self.probe = True
            self.active.add(key)
            self.calls.append(now)
            return "allowed", None

    def finish(self, key, value=None):
        with self.lock:
            self.active.discard(key)
            if value is not None:
                self.failures = 0
                self.open_until = None
                self.probe = False
                self.cache[key] = (self.clock() + 300, dict(value))
                self.cache.move_to_end(key)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
            else:
                self.failures += 1
                if self.probe or self.failures >= 3:
                    self.open_until = self.clock() + 30
                self.probe = False


GUARD = HintGuard()


def reset():
    """Reset process state for isolated tests; do not reset while requests run."""
    global GUARD
    GUARD = HintGuard()
