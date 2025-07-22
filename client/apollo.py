import logging
from apollo_client import ApolloClient


logger = logging.getLogger(__name__)


class Apollo:
    def __init__(self, appid, config_server_url, cluster="default", _notification_map=None, base_path=None, shared_cache=True):
        self.appid = appid
        self.config_url = config_server_url
        self.apollo = ApolloClient(config_url=self.config_url, app_id=self.appid, cluster=cluster,
                                   _notification_map=_notification_map, base_path=base_path, shared_cache=shared_cache)

    def get_value(self, key, namespace="application"):
        """
        获取指定appid下指定namespace下的指定key的值
        :return: value
        """
        try:
            return self.apollo.get_value(key=key, namespace=namespace)
        except Exception as e:
            logger.error(f"get_value error: {e}")
            return None

    def get_all_values_no_cache(self, namespace="application"):
        """
        通过不带缓存的Http接口从Apollo读取配置
        :return: 指定namespace下的全部数据 dict
        """
        return self.apollo.cache[namespace]


if __name__ == "__main__":
    appid = "python-etax"
    config_server_url = "http://"

    notification_map = {'application': -1, "ns.python.public.config": -1}
    apollo = Apollo(appid, config_server_url, _notification_map=notification_map)
    apollo.get_value("username")
