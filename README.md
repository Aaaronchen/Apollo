# Apollo
## python apollo-client



1. 客户端和服务端保持了一个长连接，从而能第一时间获得配置更新的推送。（通过Http Long Polling实现）
2. 客户端还会定时从Apollo配置中心服务端拉取应用的最新配置。    
3. 这是一个fallback机制，为了防止推送机制失效导致配置不更新
4. 客户端定时拉取会上报本地版本，所以一般情况下，对于定时拉取的操作，服务端都会返回304 - Not Modified
5. 定时频率默认为每5分钟拉取一次，客户端也可以通过在运行时指定System Property: apollo.refreshInterval来覆盖，单位为分钟。
6. 客户端从Apollo配置中心服务端获取到应用的最新配置后，会保存在内存中
7. 客户端会把从服务端获取到的配置在本地文件系统缓存一份    
8. 在遇到服务不可用，或网络不通的时候，依然能从本地恢复配置
9. 应用程序可以从Apollo客户端获取最新的配置、订阅配置更新通知



----------

----------

- 支持本地缓存

- 支持多个namespaces

- 支持内存共享功能、便于在celery等pre_fork方式的框架中实时更新


-----------

----------


项目对比：

1. https://github.com/filamoon/pyapollo/blob/master/pyapollo/apollo_client.py  简洁明了，适合刚上手阅读使用，功能欠缺

2. https://github.com/BruceWW/pyapollo/blob/master/pyapollo/apollo_client.py  基于1做了优化，补充了本地化配置的存储，但是删减了Longpoll的真实使用意图

3. https://github.com/xhrg-product/apollo-client-python/blob/master/apollo/apollo_client.py 比较冗余，longpoll和getvalue的逻辑增加了不必要的心跳
