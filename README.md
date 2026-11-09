# sub-egress · 出站网关与多内核订阅调度中枢

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.17-blue.svg" alt="version">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/database-PostgreSQL%20%7C%20SQLite-336791.svg" alt="Database">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license">
</p>

**sub-egress** 是一个面向个人极客与企业基础设施的现代化跨机场出站网关与订阅聚合调度平台。

彻底废弃黑盒抽屉逻辑，采用**纯粹二元制单一节点选择体系**与**带严格国家/属性边界的动态健康巡检**，原生支持 **Mihomo (ClashMeta)**、**Sing-box** 与 **Universal Base64** 订阅分发。

---

## 🌟 核心设计理念 (Core Architecture)

### 1. 风格 B 双端口出站与绝对透明掌控 (Dual Ports & Direct Proxying)
大部分传统订阅转换器强制在服务端预设复杂臃肿的网站分流规则，导致客户端无法自主选择。`sub-egress` 采用风格 B 双端口双出站体系：
- **`[7897] 主出站`**：默认直通主端口，开箱预选 `[动态·家宽]`（纯净住宅 IP 智能主备），专为风控敏感的 AI 工具与主干业务设计。
- **`[7898] 副出站`**：默认直通副端口（如通过 listeners 绑定），开箱预选 `[动态·日区]`（低延迟超大带宽），供日常高吞吐、大流量与流媒体场景自由取用。
- **透明平铺调度**：两个出站组均完全平铺供应商专区、地区智能组以及物理单节点，随时在客户端自由点选切换。
- **局域网与国内直连**：`GEOIP, CN`、私有网段自动直连 (`DIRECT`)，纯净极简。

### 2. 四层递进式节点管理体系 (4-Tier Hierarchy)
- **第一层 · 双端口出站门神**：`[7897] 主出站` 与 `[7898] 副出站`，主副端口独立映射。
- **第二层 · 供应商专区 (Source Groups)**：如 `[源·RE] 🇺🇸 RESIP 美国家宽专区`、`[源·SD] 🌐 SDK 机场全节点专区`，按机场聚合调度。
- **第三层 · 边界隔离动态组 (Boundary-Isolated Dynamic Groups)**：如 `[动态·日区] 🇯🇵`、`[动态·家宽] 🇺🇸`、`[动态·全局] 🌐`，同国/同属性硬边界巡检，绝不跨区乱跳。
- **第四层 · 物理单节点池 (Physical Nodes)**：彻底移除“透传”赘字，采用 `[两位供应商代码] 国旗 名字 协议 倍率` 极简规范（如 `[RE] 🇺🇸 美国-01 A 住宅主线`，`[SD] 🇯🇵 日本-01 S 1.0x`，台湾节点统一五星红旗 `🇨🇳`，全局单国旗渲染）。

### 3. 多内核原生支持 (ClashMeta + Sing-box)
- **Mihomo / ClashMeta**：生成标准化精简 YAML 配置 (`?target=clash`)。
- **Sing-box**：生成包含 DNS 独立解析、Mixed Inbound、Outbound Selector 与 Route 规则的完整 JSON (`?target=sing-box`)。
- **Base64 / URI**：支持标准 Shadowsocks、VLESS Reality、Trojan、Hysteria2 节点链接串导出 (`?target=base64`)。

### 4. 纯粹通用与配置解耦 (100% Decoupled & Open Source)
- 代码库 100% 通用，无任何私有域名或企业内部 DNS 硬编码。
- 支持在管理后台动态注入自定义直连域名与 DNS 策略，订阅导出端点自动感应客户端请求 Host 头。
- 下游订阅支持基于混淆 Hash Token 的专属端点：
  ```
  https://<your-domain>/c/<hash_token>?target=clash
  https://<your-domain>/c/<hash_token>?target=sing-box
  ```

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
