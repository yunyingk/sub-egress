# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2026-11-09

### Added
- **Traffic Usage & Billing Cycle Extraction**: Extract cycle reset days (e.g. `29 天后重置`) and remaining quota from subscription text/headers.
- **Enhanced Traffic Visuals**: Card progress bar and percentage display clarifying 0 B usage upon monthly quota resets.
- **Automated Gitea & Infra GitOps Pipeline**: Integrated with personal `infra` deployment repository. Pushing tags triggers automatic building and K3s rollout via `watch.sh`.
- **Zero-Config Localhost & SQLite Support**: Seamlessly runs on localhost or single container with automatic SQLite fallback when no PostgreSQL is provided.

## [0.2.0] - 2026-11-09

### Added
- **Multi-Target Kernel Distribution**: Native support for Mihomo/Clash (`?target=clash`), Sing-box (`?target=sing-box`), and Universal Base64 (`?target=base64`).
- **Subscription Hash Security Token**: Secure hashed subscription endpoint `/c/{token}?target={target}` preventing random internet probing.
- **Read/Write Security Settings**: Built-in modal and API (`/api/settings`) to configure token enforcement, API management keys, default targets, and update intervals.
- **Clean Light Theme**: Default Apple/Tailwind white theme with smooth dark/light mode toggle and `localStorage` persistence.
- **PWA Service Worker Cleanup**: Automatic detection and unregistration of legacy Sub-Store offline service workers.

### Changed
- Standardized project structure for GitHub open-source release with MIT License and Semantic Versioning.
- Upgraded ingress routing on WSL host to support direct `/c/{token}`, `/sub/{token}`, and `/download/*` bypass for client updaters.

## [0.1.0] - 2026-11-09

### Added
- Initial release of `sub-egress`.
- High-performance FastAPI backend with PostgreSQL 18 persistence.
- Binary single-selector rule model (`DIRECT` for China/LAN, `PROXY` for foreign traffic).
- Boundary-isolated dynamic groups:
  - `[动态·日区]` (Japan lowest latency, strict zero cross-region hops).
  - `[动态·家宽]` (US clean residential IP failover).
  - `[动态·全局]` (Global disaster recovery failover).
- Direct physical passthrough node flattening (56+ nodes).
- Web dashboard with Vue 3 and Tailwind CSS.
- Kubernetes K3s deployment manifest.
