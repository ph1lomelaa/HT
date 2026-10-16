"""Bounded, expiring in-memory sessions and opaque callback references."""
import time
import uuid


class SessionCache(dict):
    def __init__(self, ttl=3600, maxsize=2000):
        super().__init__()
        self.ttl, self.maxsize, self.deadlines = ttl, maxsize, {}

    def purge(self):
        for key, deadline in list(self.deadlines.items()):
            if deadline <= time.monotonic():
                self.pop(key, None)

    def __setitem__(self, key, value):
        self.purge()
        if key not in self and len(self) >= self.maxsize:
            self.pop(next(iter(self)), None)
        super().__setitem__(key, value)
        self.deadlines[key] = time.monotonic() + self.ttl

    def get(self, key, default=None):
        if self.deadlines.get(key, 0) <= time.monotonic():
            self.pop(key, None)
        return super().get(key, default)

    def pop(self, key, default=None):
        self.deadlines.pop(key, None)
        return super().pop(key, default)

    def clear(self):
        self.deadlines.clear()
        super().clear()


CALLBACKS = SessionCache()


def callback_ref(prefix, *values):
    key = uuid.uuid4().hex[:16]
    CALLBACKS[key] = values
    return f'{prefix}:{key}'


def resolve_callback(data, prefix):
    if not data.startswith(prefix + ':'):
        raise ValueError('Некорректная кнопка')
    value = CALLBACKS.get(data.split(':', 1)[1])
    if value is None:
        raise ValueError('Кнопка устарела. Выберите месяц заново.')
    return value
