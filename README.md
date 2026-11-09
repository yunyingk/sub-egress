# sub-egress · 出站网关与多内核订阅调度中枢

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.11-blue.svg" alt="version">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/database-PostgreSQL%20%7C%20SQLite-336791.svg" alt="Database">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license">
</p>

**sub-egress** 是一个面向个人极客与企业基础设施的现代化跨机场出站网关与订阅聚合调度平台。

彻底废弃黑盒抽屉逻辑，采用**纯粹二元制单一节点选择体系**与**带严格国家/属性边界的动态健康巡检**，原生支持 **Mihomo (ClashMeta)**、**Sing-box** 与 **Universal Base64** 订阅分发。

---

## 🌟 核心设计理念 (Core Architecture)

### 1. 极简二元制单一节点选择 (Binary Selector)
大部分传统订阅转换器强制在服务端预设复杂臃肿的网站分流规则，导致客户端无法自主选择。`sub-egress` 坚持极简二元原则：
- **局域网与国内直连**：`GEOIP, CN`、私有网段自动直连 (`DIRECT`)。
- **全量外网代理**：所有境外流量一律汇聚到单一主选择器 `PROXY`。
- **客户端绝对掌控**：用户在客户端点选哪个节点，全部外网流量就走哪个节点，清晰透明。

### 2. 边界隔离动态组 (Boundary-Isolated Dynamic Groups)
为了防止传统自动化测试在故障时盲目“跨国漂移”导致业务会话中断，`sub-egress` 内置带硬边界的动态测试组：
- **`[动态·日区] 🇯🇵 日本最佳低延迟`**：严格锁定同国节点测速，绝不跨区乱跳。
- **`[动态·家宽] 🇺🇸 美国住宅智能主备`**：严格锁定纯净美国家宽节点，主备无缝切换，绝不混入机房 IP。
- **`[动态·全局] 🌐 全网故障转移`**：全量可用节点的最终兜底。
- **`[透传·{机场名}] ...`**：平铺所有物理节点，带有清晰前缀，方便客户端直接点选。

### 3. 多内核原生支持 (ClashMeta + Sing-box)
- **Mihomo / ClashMeta**：生成标准化精简 YAML 配置 (`?target=clash`)。
- **Sing-box**：生成包含 DNS 独立解析、Mixed Inbound、Outbound Selector 与 Route 规则的完整 JSON (`?target=sing-box`)。
- **Base64 / URI**：支持标准 Shadowsocks、VLESS Reality、Trojan、Hysteria2 节点链接串导出 (`?target=base64`)。

### 4. 订阅安全 Hash 令牌与读写访问控制
- 下游订阅支持基于混淆 Hash Token 的专属端点：
  ```
  https://sub.ying-qing.cn/c/<hash_token>?target=clash
  https://sub.ying-qing.cn/c/<hash_token>?target=sing-box
  ```
- 内置「读写设置」中心，支持强制安全令牌访问阻断公网探测，支持自定义管理写入 API Key。

---

## 🚀 启动与部署方式 (Deployment)

`sub-egress` 支持零配置极简启动与生产级企业集群部署：

### 方式 1：Docker 一键单容器启动 (零依赖，内置 SQLite)
适合任何只需要单机跑起来的用户，无需预装任何外部数据库：
```bash
docker run -d \
  --name sub-egress \
  -p 8000:8000 \
  -v sub_data:/data \
  --restart unless-stopped \
  yunyingk/sub-egress:latest
```
访问 `http://localhost:8000` 即可立即进入 Web 控制台。

---

### 方式 2：Docker Compose (支持 SQLite 或自带 PostgreSQL 18)
项目根目录已附带开箱即用的 [`docker-compose.yml`](docker-compose.yml)：
```bash
# 1. 克隆项目
git clone https://github.com/yunyingk/sub-egress.git && cd sub-egress

# 2. 启动服务 (默认使用内置持久化卷)
docker compose up -d
```
如需外接 PostgreSQL，可在 `docker-compose.yml` 中解开 `DATABASE_URL` 注释或解开自带的 `postgres` 容器服务。

---

### 方式 3：Kubernetes / K3s 集群部署 (推荐生产使用)
项目提供了 [`k8s/`](k8s/) 原生资源清单，已支持通过 Secret 挂载 PostgreSQL 连接串：
```bash
# 1. 配置数据库连接 Secret (参考 k8s/secret.example.yaml)
kubectl apply -f k8s/secret.example.yaml

# 2. 部署服务与 Service
kubectl apply -f k8s/deployment.yaml
```

**PostgreSQL 连接串格式说明**：
* 必须使用异步驱动前缀：`postgresql+asyncpg://<user>:<password>@<host>:5432/<dbname>`
* 若传入标准 `postgresql://` 或 `postgres://`，系统会自动内部转换为 `postgresql+asyncpg://`。

---

## 📄 License
Released under the [MIT License](LICENSE).
