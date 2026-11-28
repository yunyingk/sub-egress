# sub-egress · 出站网关与多内核订阅调度中枢

<p align="center">
  <a href="https://github.com/yunyingk/sub-egress/releases"><img src="https://img.shields.io/github/v/release/yunyingk/sub-egress?label=version" alt="version"></a>
  <a href="https://github.com/yunyingk/sub-egress/actions/workflows/ci.yml"><img src="https://github.com/yunyingk/sub-egress/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.14%2B-blue.svg" alt="python">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/database-PostgreSQL%20%7C%20SQLite-336791.svg" alt="Database">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="license">
</p>

**sub-egress** 是一个面向个人极客与企业基础设施的现代化跨机场出站网关与订阅聚合调度平台。

彻底废弃黑盒抽屉逻辑，采用**纯粹二元制单一节点选择体系**与**带严格国家/属性边界的动态健康巡检**，原生支持 **Mihomo (ClashMeta)**、**Sing-box** 与 **Universal Base64** 订阅分发。

---

## 🌟 核心设计理念 (Core Architecture)

### 1. 多组精准分流与双端口出站 (Dual Ports & Explicit Premium Isolation)
大部分传统订阅转换器容易把高成本住宅/洁净线路混入日常出站，导致普通流量误消耗。`sub-egress` 采用**普通日常与精选高级彻底隔离**的透明调度体系：
- **`[7897] 主出站`**：默认直通主端口与移动端 TUN，开箱预选 `[动态·全局] 🌐 日常全网优选`（纯普通节点），承担常规海外流量与 `MATCH` 兜底。
- **`精选高级`**：专为网页后台显式标记为 `精选高级`（`premium`）的高纯度/家宽源设立，开箱预选 `[动态·精选高级] ⭐ 精选高级主备`，自动承接主流 AI / 高风控域名与后台热追加的高级域名。
- **`[7898] 副出站`**：绑定本机 `127.0.0.1` 副端口的单一出口，开箱预选 `[动态·日区]`（纯普通低延迟节点），供命令行与高吞吐场景直连使用。
- **`GLOBAL`**：显式定义标准 `GLOBAL` 策略组并将首位锁定为 `[7897] 主出站`，防止客户端切换全局模式时误烧高级线路流量。
- **局域网与国内直连**：`GEOIP, CN`、私有网段自动直连 (`DIRECT`)，纯净极简。

### 2. 四层递进式节点管理体系 (4-Tier Hierarchy)
- **第一层 · 门神策略组**：`[7897] 主出站`、`精选高级`、`[7898] 副出站` 与 `GLOBAL`，职责边界清晰。
- **第二层 · 供应商专区 (Source Groups)**：按 `[代码]` 前缀与源等级（普通专区 vs 精选高级专区）聚合调度，随时整体切换供应商。
- **第三层 · 边界隔离动态组 (Boundary-Isolated Dynamic Groups)**：港区、日区、狮城、美区等普通地区优选组与 `[动态·精选高级]` 主备组严格隔离，绝不跨区或跨等级混用。
- **第四层 · 物理单节点池 (Physical Nodes)**：采用 `[供应商代码] 国旗 节点名` 规范，支持后台白名单授权指定用户可见。

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

`sub-egress` 支持真正的**零门槛一键启动**与**生产级企业高可用部署**：

### 方式 1：Docker Compose 一键启动 (最简推荐，零外部依赖)
项目根目录已附带开箱即用的 [`docker-compose.yml`](docker-compose.yml)，默认自动采用嵌入式轻量 SQLite 数据库，单机资源占用仅数十兆：
```bash
# 1. 克隆项目仓库
git clone https://github.com/yunyingk/sub-egress.git && cd sub-egress

# 2. 一键启动服务
docker compose up -d

# 3. 查看自动生成的初始管理员 admin 密码
docker compose logs sub-egress
```
浏览器访问 `http://localhost:8000` 即可直接进入单页认证门户！

使用通行密钥前，需设置 `WEBAUTHN_ORIGIN` 为浏览器实际访问的完整来源（例如 `https://sub.example.com`；本地开发可用 `http://localhost:8000`），并确保反向代理保留原始 Host。未配置时，通行密钥接口返回 503，密码登录不受影响。升级已有部署时先配置此值；旧版本可能虚增通行密钥计数器，需先核对已有凭证并准备备用登录方式。

---

### 方式 2：Docker 单容器一键运行
```bash
docker run -d \
  --name sub-egress \
  -p 8000:8000 \
  -v ./data:/data \
  --restart unless-stopped \
  ghcr.io/yunyingk/sub-egress:latest

# 查看初始密码
docker logs sub-egress
```

---

### 方式 3：本地 Python 源码免 Docker 启动
如果您不想使用 Docker，也可以直接在个人 Mac / Linux / Windows WSL 上使用 Python 运行：
```bash
git clone https://github.com/yunyingk/sub-egress.git && cd sub-egress
uv sync --locked --extra dev
uv run --locked uvicorn app.main:app --host 0.0.0.0 --port 8000
```

也可以不安装 uv，使用 Python 3.14 的虚拟环境和从锁文件导出的依赖清单：
```bash
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
PYTHONPATH=backend python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Windows 可改用 `.venv\\Scripts\\activate` 并设置相应的 `PYTHONPATH`。更新依赖时先更新 `uv.lock`，再用 `uv export --locked --no-dev --no-emit-project --no-hashes --no-header -o backend/requirements.txt` 同步导出文件。

旧版数据库升级前请阅读 [UTC 时间迁移说明](docs/UTC时间迁移.md)。PostgreSQL 中旧版无时区时间列必须先确认原始时区并迁移，否则新版会拒绝启动。

---

### 🔐 账号体系与管理员应急恢复

1. **初始管理员 (admin)**：
   - 系统首次启动时会自动初始化 `admin` 账号，生成 32 位符合全小写规范（严禁大写字母）的加密强随机密码，并在控制台日志中显性展示。
2. **忘记密码应急重置**：
   - **方式 A (环境变量)**：重启容器并传入环境变量 `RESET_ADMIN_PASSWORD="<新全小写密码>"` 即可自动重设。
   - **方式 B (内置 CLI)**：在终端或容器内执行 `python -m app.manage reset-admin`，一键重置并输出新密码。
3. **用户账号规范**：
   - 用户名：5 ~ 20 位，纯小写字母与数字。
   - 密码：20 ~ 260 位，纯小写字母 + 数字 + 符号（严禁大写字母）。
   - 通行密钥 (Passkey)：每账号最多绑定 5 个，全周期记录创建与最后验签时间。
   - 第三方登录：支持 Authentik SSO 单点登录与防自锁解绑。

---

### 方式 4：Kubernetes / K3s 生产集群部署 (PostgreSQL 18)
生产环境推荐依托外部 PostgreSQL 18 并使用项目自带的 [`k8s/`](k8s/) 清单：
```bash
# 1. 配置数据库连接 Secret (参考 k8s/secret.example.yaml)
kubectl apply -f k8s/secret.example.yaml

# 2. 部署服务与 Service
kubectl apply -f k8s/deployment.yaml
```

**PostgreSQL 连接串格式说明**：
* 推荐异步驱动前缀：`postgresql+asyncpg://<user>:<password>@<host>:5432/<dbname>`
* 若传入标准 `postgresql://` 或 `postgres://`，系统会自动内部转换为 `postgresql+asyncpg://`。

---

## 📄 License
Released under the [MIT License](LICENSE).
