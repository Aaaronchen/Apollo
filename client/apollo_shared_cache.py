import json
from multiprocessing import Array, Lock
from collections.abc import MutableMapping


class SharedDict(MutableMapping):
    def __init__(self, size=4096):
        """
        :param size: 共享内存大小（字节），需预估配置JSON字符串的最大长度
        """
        self._array = Array('c', size)  # 字符数组
        self._lock = Lock()
        # self._file_lock = open('/tmp/SharedConfig.lock', 'w')  # 跨进程文件锁

    def _acquire_locks(self):
        """上下文管理器，同时获取文件锁和线程锁"""

        class LockContext:
            def __enter__(_self):
                # fcntl.flock(self._file_lock, fcntl.LOCK_EX)
                self._lock.acquire()

            def __exit__(_self, *args):
                self._lock.release()
                # fcntl.flock(self._file_lock, fcntl.LOCK_UN)

        return LockContext()

    def _clear_memory(self):
        """清空共享内存"""
        self._array[:] = b'\x00' * len(self._array)

    @staticmethod
    def _serialize(data):
        """序列化数据为字节"""
        return json.dumps(data).encode('utf-8')

    @staticmethod
    def _deserialize(bytes_data):
        """从字节反序列化数据"""
        return json.loads(bytes_data.decode('utf-8')) if bytes_data else {}

    def __setitem__(self, key, value):
        """支持 config['key'] = value 操作"""
        with self._acquire_locks():
            current = self._deserialize(bytes(self._array[:]).split(b'\x00')[0])
            current[key] = value
            serialized = self._serialize(current)

            if len(serialized) > len(self._array):
                raise ValueError("配置数据超出共享内存容量")

            self._clear_memory()
            self._array[:len(serialized)] = serialized

    def __getitem__(self, key):
        """支持 value = config['key'] 操作"""
        return self._deserialize(bytes(self._array[:]).split(b'\x00')[0])[key]

    def __delitem__(self, key):
        """支持 del config['key'] 操作"""
        with self._acquire_locks():
            current = self._deserialize(bytes(self._array[:]).split(b'\x00')[0])
            del current[key]
            serialized = self._serialize(current)

            self._clear_memory()
            self._array[:len(serialized)] = serialized

    def __iter__(self):
        """支持 for key in config 操作"""
        return iter(self._deserialize(bytes(self._array[:]).split(b'\x00')[0]))

    def __len__(self):
        """支持 len(config) 操作"""
        return len(self._deserialize(bytes(self._array[:]).split(b'\x00')[0]))

    def __contains__(self, key):
        """支持 'key' in config 操作"""
        return key in self._deserialize(bytes(self._array[:]).split(b'\x00')[0])

    def __repr__(self):
        """支持 print(config) 操作"""
        return repr(self._deserialize(bytes(self._array[:]).split(b'\x00')[0]))

    def update(self, *args, **kwargs):
        """支持 dict-like 的 update 方法"""
        with self._acquire_locks():
            current = self._deserialize(bytes(self._array[:]).split(b'\x00')[0])
            current.update(*args, **kwargs)
            serialized = self._serialize(current)

            if len(serialized) > len(self._array):
                raise ValueError("配置数据超出共享内存容量")

            self._clear_memory()
            self._array[:len(serialized)] = serialized

    def get(self, key, default=None):
        """支持 dict-like 的 get 方法"""
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self):
        """清空配置"""
        with self._acquire_locks():
            self._clear_memory()

    def copy(self):
        """返回配置的深拷贝"""
        return self._deserialize(bytes(self._array[:]).split(b'\x00')[0]).copy()


# 主进程初始化（preload_app=True时创建）
# gobal_dict = SharedDict()  # 4KB共享内存
