# Kubernetes 核心概念

## 架构

- **Master / Control Plane**：kube-apiserver / kube-scheduler / kube-controller-manager / etcd
- **Worker Node**：kubelet / kube-proxy / 容器运行时（containerd）
- 一切资源都通过 apiserver 暴露为 REST API

## 核心对象

### Pod
- 最小调度单位，包含 1+ 个容器
- 共享网络（同一 IP、同一卷）
- 一般不直接创建，由 Deployment/StatefulSet 管理

### Deployment
- 管理 Pod 副本集，支持滚动更新、回滚
- 适合无状态应用

### StatefulSet
- 稳定的网络标识与持久存储
- 适合数据库、消息队列

### Service
- 负载均衡 + 服务发现
- ClusterIP / NodePort / LoadBalancer

### ConfigMap / Secret
- 配置与敏感数据
- Secret 支持 base64 编码（不是加密）

### Ingress
- 7 层负载均衡（HTTPS / 路由 / 域名）
- 需要 Ingress Controller（nginx / traefik）

## 调度

- 节点选择：`nodeSelector` / `affinity`
- 污点与容忍：`taints` / `tolerations`
- Pod 拓扑：`topologySpreadConstraints`

## 自动伸缩

- HPA：基于 CPU / 内存 / 自定义指标
- VPA：调整 Pod 资源 request
- Cluster Autoscaler：节点级伸缩

## 服务网格

- Istio / Linkerd：sidecar 代理，处理 mTLS、流量管理、可观测性
- 不修改业务代码即可获得金丝雀发布、熔断、链路追踪

## 工程经验

- 资源 request/limit 必须设置（否则调度器无法合理分配）
- 探针（liveness/readiness/startup）配置：避免无限重启
- PodDisruptionBudget：保证滚动升级时可用副本数
