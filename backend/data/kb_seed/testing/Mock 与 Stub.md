# Mock 与 Stub

## 核心区别

### Stub（桩）
返回预设的硬编码值，**只**验证请求能到达 + 响应可处理。
被测代码 → Stub（只读）

### Mock（替身）
可以验证「调用是否发生、调用了几次、参数是什么」。
被测代码 ↔ Mock（双向断言）

Martin Fowler：「Mock 与 Stub 的区别在于测试期望如何被验证」。

## 何时用

### 单元测试
- 外部依赖：HTTP API、消息队列、数据库
- 时间 / 随机数：固定值可重现
- 未完成的下游：隔离并行开发

### 集成测试
慎用 mock——集成测试的目的就是验证模块协作。
只在跨进程外部服务上 mock。

## Python 工具

### unittest.mock
```python
from unittest.mock import Mock, patch
mock_db = Mock()
mock_db.query.return_value = [{"id": 1}]
with patch("module.external_api")") as m:
    m.return_value = {"ok": True}
    result = func_under_test()
```

### pytest-mock
```python
def test_x(mocker):
    mock = mocker.patch("module.func")
    mock.return_value = 42
```

### responses（HTTP mock）
```python
import responses
@responses.activate
def test_api():
    responses.add(responses.GET, "https://api.example.com",
                  json={"ok": True}, status=200)
```

## 反模式

- 过度 mock：测试只验证了你的 mock 行为
- 脆弱 mock：mock 内部实现细节，重构就崩
- 全网络 mock：集成测试失去意义
- 期望调用次数：耦合到实现，难以维护

## 替代方案

- 契约测试（Pact）：mock 由消费方定义、提供方验证
- 测试容器：起真实依赖的临时实例
- 内存实现：被测对象的接口有内存版（最干净的依赖反转）
