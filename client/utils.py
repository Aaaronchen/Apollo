import logging
import hashlib


logger = logging.getLogger(__name__)


def signature(timestamp, uri, secret):
    # 对时间戳，uri，秘钥进行加签
    import hmac
    import base64
    string_to_sign = '' + timestamp + '\n' + uri
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(hmac_code).decode()


# 返回是否获取到的值，不存在则返回None
def get_value_from_dict(namespace_cache, key):
    if namespace_cache:
        if namespace_cache is None:
            return None
        if key in namespace_cache:
            return namespace_cache[key]
    return None


def listener(change_type, namespace, key, value):
    logger.info(f"Namespace {namespace}, has {change_type} key: {key}, value: {value}")
