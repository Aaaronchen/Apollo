import hashlib
import json
import os
import socket
import logging
import threading
import time
import requests

from pathlib import Path
from urllib import parse

from utils import signature
from utils import get_value_from_dict
from apollo_shared_cache import SharedDict


logger = logging.getLogger(__name__)


class ApolloClient(object):

    def __init__(self, config_url, app_id, cluster='default', secret='', start_hot_update=True,
                 change_listener=None, _notification_map=None, ip=None, base_path=None, shared_cache=True):

        self._cache = dict()
        if shared_cache:
            self._cache = SharedDict(size=4096 * 10 * 3)

        # 核心路由参数
        self.config_url = config_url
        self.cluster = cluster
        self.app_id = app_id

        # 非核心参数
        self.ip = self.init_ip(ip)
        self.secret = secret

        # 私有控制变量
        self._cycle_time = 2
        self._stopping = False
        # self._cache = {}
        self._no_key = {}
        self._hash = {}
        self._pull_timeout = 75
        if base_path is None:
            base_path = Path().cwd()
        self._cache_file_path = str(Path.joinpath(base_path, 'apollo/cache'))
        self._long_poll_thread = None
        self._change_listener = change_listener  # "add" "delete" "update"
        if _notification_map is None:
            _notification_map = {'application': -1}
        self._notification_map = _notification_map
        self.last_release_key = None
        # 私有启动方法
        self._path_checker()
        self.start(start_hot_update)

        # 启动心跳线程、_long_poll的notifications请求不会更新apollo的实例连接，但不影响实际使用
        # heartbeat = threading.Thread(target=self._heart_beat)
        # heartbeat.setDaemon(True)
        # heartbeat.start()

    @property
    def cache(self):
        return self._cache

    @staticmethod
    def init_ip(ip):
        if not ip:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3)
                    s.connect(('8.8.8.8', 53))
                    ip = s.getsockname()[0]
            except Exception as e:
                logger.error(f"init_ip connect socket error: {e}")
        return ip

    def get_json_from_net(self, namespace='application'):
        url = f'{self.config_url}/configs/{self.app_id}/{self.cluster}/{namespace}?releaseKey=""&ip={self.ip}'
        try:
            res = requests.get(url, timeout=5, headers=self._sign_headers(url))
            if res.status_code == 200:
                data = res.json()
                data = data.get("configurations") or dict()
                return data
            else:
                return None
        except Exception as e:
            logger.error(f"get_json_from_net error: {e}")
            return None

    def get_value(self, key, default_val=None, namespace='application'):
        try:
            if namespace not in self._notification_map:
                self._notification_map[namespace] = -1
                logger.info(f"Add namespace {namespace} to local notification map")
            if namespace not in self._cache:
                self._cache[namespace] = {}
                logger.info(f"Add namespace {namespace} to local cache")
                self._long_poll()

            # 读取内存配置
            namespace_cache = self._cache.get(namespace)
            val = get_value_from_dict(namespace_cache, key)
            if val is not None:
                return val

            # 从其他namespace获取配置
            for _cache_key, _cache_value in self._cache.items():
                if key in _cache_value:
                    logger.info(
                        f"key {key} is not in namespace {namespace}, "
                        f"instead of namespace {_cache_key} to get_value: {_cache_value[key]}")
                    return _cache_value[key]

            return default_val
        except Exception as e:
            logger.error(f"get_value has error, [key is {key}], [namespace is {namespace}], [error is {e}]")
            return default_val

    def start(self, start_hot_update):
        if not self._long_poll():  # 初始化时请求失败则读取文件配置
            for namespace in self._notification_map:
                self._get_local_and_set_cache(namespace)
        if start_hot_update:
            self._long_poll_thread = threading.Thread(target=self._listener)
            self._long_poll_thread.setDaemon(True)
            self._long_poll_thread.start()

    def stop(self):
        self._stopping = True
        logger.info("Stopping listener...")

    # 调用设置的回调函数，如果异常，直接try掉
    def _call_listener(self, namespace, old_kv, new_kv):
        if self._change_listener is None:
            return
        if old_kv is None:
            old_kv = {}
        if new_kv is None:
            new_kv = {}
        try:
            for key in old_kv:
                new_value = new_kv.get(key)
                old_value = old_kv.get(key)
                if new_value is None:
                    # 如果newValue 是空，则表示key，value被删除了。
                    self._change_listener("delete", namespace, key, old_value)
                    continue
                if new_value != old_value:
                    self._change_listener("update", namespace, key, new_value)
                    continue
            for key in new_kv:
                new_value = new_kv.get(key)
                old_value = old_kv.get(key)
                if old_value is None:
                    self._change_listener("add", namespace, key, new_value)
        except BaseException as e:
            logger.error(f"_call_listener error: {e}")

    def _path_checker(self):
        if not os.path.isdir(self._cache_file_path):
            os.makedirs(self._cache_file_path, exist_ok=True)

    def _update_cache_and_file(self, namespace_data, namespace='application'):
        # 更新本地缓存
        self._cache[namespace] = namespace_data
        logger.info(f'Updated local cache for namespace {namespace}: {repr(self._cache[namespace])}')
        # 更新文件缓存
        new_string = json.dumps(namespace_data)
        new_hash = hashlib.md5(new_string.encode('utf-8')).hexdigest()
        if self._hash.get(namespace) == new_hash:
            pass
        else:
            with open(os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace)),
                      'w') as f:
                f.write(new_string)
            self._hash[namespace] = new_hash
            logger.info(f'Updated local configfile for namespace {namespace}')

    # 从本地文件获取配置
    def _get_local_cache(self, namespace='application'):
        cache_file_path = os.path.join(self._cache_file_path, '%s_configuration_%s.txt' % (self.app_id, namespace))
        if os.path.isfile(cache_file_path):
            with open(cache_file_path, 'r') as f:
                result = json.loads(f.readline())
            return result
        return {}

    def _long_poll(self):
        notifications = []
        for key in self._notification_map:
            notification_id = self._notification_map[key]
            notifications.append({
                "namespaceName": key,
                "notificationId": notification_id
            })
        try:
            # 如果长度为0直接返回
            if len(notifications) == 0:
                return False
            url = f'{self.config_url}/notifications/v2'
            params = {
                'appId': self.app_id,
                'cluster': self.cluster,
                'notifications': json.dumps(notifications, ensure_ascii=False)
            }
            param_str = parse.urlencode(params)
            url = url + '?' + param_str
            res = requests.get(url, timeout=self._pull_timeout, headers=self._sign_headers(url))
            if res.status_code == 304:
                logger.debug('No change, loop...')
            elif res.status_code == 200:
                data = res.json()
                get_net_result_list = []
                for entry in data:
                    namespace = entry["namespaceName"]
                    n_id = entry["notificationId"]
                    logger.info(f"Namespace {namespace} has changes: notificationId={n_id}")
                    get_net_result = self._get_net_and_set_local(namespace, n_id, call_change=True)
                    get_net_result_list.append(not get_net_result)
                if all(get_net_result_list):  # 全是False时返回False
                    return False
            else:
                logger.debug('Sleep...')
            return True
        except Exception as e:
            logger.error(f"_long_poll error: {e}")
            return False

    def _get_net_and_set_local(self, namespace, n_id, call_change=False):
        self._notification_map[namespace] = n_id
        namespace_data = self.get_json_from_net(namespace)
        if namespace_data is None:  # 没有获取到则不覆盖
            return False
        old_namespace = self._cache.get(namespace)
        self._update_cache_and_file(namespace_data, namespace)
        if self._change_listener is not None and call_change:
            self._call_listener(namespace, old_namespace, namespace_data)
        return True

    def _get_local_and_set_cache(self, namespace):
        namespace_data = self._get_local_cache(namespace)
        self._cache[namespace] = namespace_data
        logger.info(f'Updated local cache from local configfile for namespace {namespace}')
        logger.info(f'Updated local cache for namespace {namespace}: {repr(self._cache[namespace])}')

    def _listener(self):
        logger.debug('Entering listener loop...')
        while not self._stopping:
            self._long_poll()
            time.sleep(self._cycle_time)
        logger.debug("Listener stopped!")

    def _sign_headers(self, url):
        # 给header增加加签需求
        headers = {}
        if self.secret == '':
            return headers
        uri = url[len(self.config_url):len(url)]
        time_unix_now = str(int(round(time.time() * 1000)))
        headers['Authorization'] = 'Apollo ' + self.app_id + ':' + signature(time_unix_now, uri, self.secret)
        headers['Timestamp'] = time_unix_now
        return headers

    def _heart_beat(self):
        while not self._stopping:
            for namespace in self._notification_map:
                self._do_heart_beat(namespace)
            time.sleep(60 * 10)  # 10分钟

    def _do_heart_beat(self, namespace):
        url = f'{self.config_url}/configs/{self.app_id}/{self.cluster}/{namespace}?ip={self.ip}'
        try:
            res = requests.get(url, timeout=5, headers=self._sign_headers(url))
            if res.status_code == 200:
                data = res.json()
                if self.last_release_key == data["releaseKey"]:
                    return None
                self.last_release_key = data["releaseKey"]
                data = data["configurations"]
                self._update_cache_and_file(data, namespace)
            else:
                return None
        except Exception as e:
            logger.error(f"_do_heartBeat error: {e}")
            return None
