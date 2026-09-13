# RESTful API 设计

## 资源建模

URL 表示**资源**（名词），HTTP 方法表示**动作**（动词）：
- `GET /users` 列表
- `GET /users/123` 详情
- `POST /users` 创建
- `PUT /users/123` 全量更新
- `PATCH /users/123` 部分更新
- `DELETE /users/123` 删除

## 状态码

- 2xx 成功：200 OK / 201 Created / 204 No Content
- 3xx 重定向：301 永久 / 302 临时 / 304 缓存
- 4xx 客户端错误：400 参数 / 401 未登录 / 403 权限 / 404 不存在 / 409 冲突 / 422 验证失败
- 5xx 服务端错误：500 / 502 网关 / 503 过载 / 504 超时

## 版本控制

- URL：`/api/v1/users`
- Header：`Accept: application/vnd.myapp.v1+json`
- 子域名：`api.v1.example.com`

推荐 URL 方式——直观、好调试。

## 过滤、排序、分页

- 过滤：`?status=active&role=admin`
- 排序：`?sort=created_at:desc`
- 分页：
  - `?page=2&size=20`（页码）
  - `?limit=20&offset=100`（偏移）
  - 游标分页：`?cursor=eyJpZCI6MTIzfQ==`（性能最好，适合无限滚动）

## 鉴权

- API Key：适合服务端调用
- JWT：适合分布式无状态
- OAuth 2.0：第三方授权
- mTLS：服务间高安全场景

## HATEOAS

返回结果里包含下一步可用的链接（link header 或字段）：
```json
{
  "data": {...},
  "links": {
    "self": "/users/123",
    "friends": "/users/123/friends"
  }
}
```
实战较少——复杂度高、收益小。

## 文档

OpenAPI（Swagger）：自动生成 API 文档与客户端 SDK。
