# sub-egress · 出站网关与多内核订阅调度中枢

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.0-blue.svg" alt="version">
  <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/database-PostgreSQL%2018-336791.svg" alt="PostgreSQL">
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
- **Mihomo / ClashMeta**：生成标准化精简 YAML 配置。
- **Sing-box**：生成包含 DNS 独立解析、Mixed Inbound、Outbound Selector 与 Route 规则的完整 JSON。
- **Base64 / URI**：支持标准 Shadowsocks、VLESS Reality、Trojan、Hysteria2 节点链接串导出。

### 4. 订阅安全 Hash 令牌与读写访问控制
- 下游订阅支持基于混淆 Hash Token 的专属端点：
  ```
  https://sub.ying-qing.cn/c/<hash_token>?target=clash
  https://sub.ying-qing.cn/c/<hash_token>?target=sing-box
  ```
- 提供“强制安全令牌访问”开关与独立的管理写入 API Key，抵御公网嗅探与扫描。

---

## 🚀 架构总览 (System Architecture)

```mermaid
flowchart TD
    subgraph Inbound["上游订阅输入 (Inbound Sources)"]
        S1["SDKDNS 主力机场"]
        S2["RESIP 纯净美国家宽"]
        S3["第三方 / 自建节点"]
    end

    subgraph Core["sub-egress 调度引擎"]
        Sync["异步同步器 (Syncer)"]
        Parser["多协议解析器 (Clash / Base64 / URI)"]
        DB[("PostgreSQL 18 共享库")]
        Builder["二元制规则组装器 (Builder)"]
        Settings["读写权限与系统设置"]
    end

    subgraph Outbound["下游专属订阅端点 (Outbound Feeds)"]
        C1["/c/{token}?target=clash (Mihomo YAML)"]
        C2["/c/{token}?target=sing-box (Sing-box JSON)"]
        C3["/c/{token}?target=base64 (Raw Base64)"]
    end

    Inbound --> Sync
    Sync --> Parser
    Parser --> DB
    DB --> Builder
    Settings --> Builder
    Builder --> Outbound
```

---

## 🛠️ 快速部署 (Deployment)

### Docker Compose
```yaml
services:
  sub-egress:
    image: yunyingk/sub-egress:v0.2.0
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql+asyncpg://dev:password@postgres:5432/sub_egress
      - FRONTEND_DIR=/frontend
    depends_on:
      - postgres

  postgres:
    image: postgres:18-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_DB=sub_egress
      - POSTGRES_USER=dev
      - POSTGRES_PASSWORD=password
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### Kubernetes (K3s)
项目内包含全套 Kubernetes 清单：
```bash
kubectl apply -f k8s/deployment.yaml
```

---

## 📄 License
Released under the [MIT License](LICENSE).
