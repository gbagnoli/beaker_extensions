import logging

from beaker.exceptions import InvalidCacheBackendError

from beaker_extensions.nosql import Container
from beaker_extensions.nosql import NoSqlManager
from beaker_extensions.nosql import pickle

try:
    import redis
    from redis import Redis
    # 2.1.0 needed for WATCH support
    # http://redis.io/commands/watch
    if [int(v) for v in redis.__version__.split(".")] < [2, 1, 0]:
        raise ImportError

except ImportError:
    raise InvalidCacheBackendError("Redis cache backend requires the 'redis' library >= 2.1.0")

log = logging.getLogger(__name__)


class RedisManager(NoSqlManager):
    def __init__(self, namespace, url=None, data_dir=None, lock_dir=None, **params):
        self.prefix = params.pop('prefix', "")
        # full_prefix is used as a key itself for storing the set of all keys
        self.full_prefix = "beaker:{0}:{1}".format(self.prefix, namespace)
        self.connection_pool = params.pop('connection_pool', None)
        NoSqlManager.__init__(self, namespace, url=url, data_dir=data_dir, lock_dir=lock_dir, **params)

    def open_connection(self, host, port, **params):
        self.db_conn = Redis(host=host, port=int(port), connection_pool=self.connection_pool, **params)

    def __contains__(self, key):
        log.debug('%s contained in redis cache (as %s) : %s'%(key, self._format_key(key), self.db_conn.exists(self._format_key(key))))
        return self.db_conn.exists(self._format_key(key))

    def set_value(self, key, value):
        key = self._format_key(key)
        pipe = self.db_conn.pipeline(transaction=True)
        pipe.set(key, pickle.dumps(value))
        pipe.sadd(self.full_prefix, key)
        pipe.execute()

    def __delitem__(self, key):
        key = self._format_key(key)
        pipe = self.db_conn.pipeline(transaction=True)
        pipe.delete(key)
        pipe.srem(self.full_prefix, key)
        res = pipe.execute()

    def _format_key(self, key=None):
        return '%s:%s' % (self.full_prefix, key.replace(' ', '\302\267'))

    def do_remove(self):
        # watch the key set so it is readable during transaction
        self.db_conn.watch(self.full_prefix)
        pipe = self.db_conn.pipeline(transaction=True)
        for key in self.keys():
            pipe.delete(key)
        pipe.delete(self.full_prefix)
        pipe.execute()

    def keys(self):
        return list(self.db_conn.smembers(self.full_prefix))


class RedisContainer(Container):
    namespace_manager = RedisManager
