# Docker 容器化基础

## 镜像与容器

- 镜像（Image）：只读模板，分层存储（Union FS）
- 容器（Container）：镜像的运行实例，顶部可写层
- Dockerfile：构建镜像的脚本

## 常用命令

```bash
docker pull nginx:latest
docker run -d -p 8080:80 --name web nginx
docker exec -it web bash
docker logs -f web
docker stop web && docker rm web
docker images
docker rmi <image-id>
docker system prune -a     # 清理
```

## Dockerfile 最佳实践

- 多阶段构建：编译阶段用完整工具链，运行阶段只带产物
- 基础镜像选小：`alpine` / `distroless` / `scratch`
- 合并 RUN 命令：`apt-get update && apt-get install ... && rm -rf /var/lib/apt/lists/*`
- COPY 在前，RUN 在后：利用缓存
- WORKDIR 而非 cd
- 非 root 用户：`USER node`

## 数据持久化

- Volume：Docker 管理的卷，推荐生产用
- Bind Mount：主机目录直挂载，适合开发
- tmpfs：内存文件系统，适合敏感数据

## 网络

- bridge：默认 NAT 网络，容器间通过容器名互通（需自定义 network）
- host：容器共用主机网络栈，性能最好
- overlay：跨主机 Swarm 集群网络

## Docker Compose

多容器编排：
```yaml
services:
  db:
    image: postgres
    volumes:
      - dbdata:/var/lib/postgresql/data
  app:
    build: .
    depends_on:
      - db
volumes:
  dbdata:
```

## 生产考虑

- 镜像签名（Docker Content Trust）
- 资源限制：`--memory` / `--cpus`
- 健康检查：`HEALTHCHECK` 指令
- 日志收集：`docker logs` 到 stdout 到 Loki/ELK
