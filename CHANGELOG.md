# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-11-10

### Added
- **AnyTLS**: Import AnyTLS links and Sing-box outbounds, and export Sing-box outbounds and Base64 share links.
- **Subscription Security**: Add a visible subscription link reset control with confirmation.

### Changed
- **Source Deletion**: Preserve source and node records in the database while hiding deleted sources from normal operations. Recovery is performed by database operators; no recycle-bin UI is provided.
- **Sing-box**: Generate one modern configuration using rule actions and remote rule sets. Rule sets are downloaded via the proxy; official 1.12.0 and 1.14.4 clients were tested. XHTTP nodes are omitted where the target format cannot represent them.

### Upgrade
- Back up the database before upgrading; startup adds soft-deletion columns to sources. First-time Sing-box startup requires a working proxy and access to its rule-set downloads.

## [0.5.1] - 2026-11-10

### Fixed
- **Subscription Export**: Restore Sing-box and Base64 node generation for the flattened node format used by the subscription API, while retaining support for nested node configurations.

## [0.5.0] - 2026-11-10

### Added
- **Account Appearance**: Save light, dark, or system appearance per user and synchronize it across devices.
- **Source Ownership**: Distinguish the private owner or platform ownership from the user who created a source.

### Fixed
- **External Identities**: Show linked providers in user administration and handle Authentik reverse-proxy identity headers.

### Changed
- **Source API**: Replace source `user_id` with `owner_user_id` and `created_by_user_id`. Historical creators remain unknown when they cannot be established.
- **Subscription Tokens**: Retire the legacy global token and prevent manually chosen user tokens. Existing administrator personal tokens remain valid. Anonymous shared subscriptions remain available when token enforcement is disabled.
- **Shared Sources**: A shared source must be enabled globally and for the user to contribute nodes or usage; globally disabled sources are hidden from the user view.

### Upgrade
- Back up the database before upgrading. Startup migrates source ownership and removes the old global token setting. Private sources without a valid owner stop the migration for manual review. Rolling back to an older application requires restoring a compatible database schema and, if needed, the backup.

## [0.4.0] - 2026-11-10

### Changed
- **Python and Dependencies**: Require Python 3.14 or later and use a reproducible uv lockfile, with an exported pip requirements file.
- **Passkey Verification**: Require an explicitly configured origin and verify origin, RP ID, credential identifiers, user presence and signature counters. Existing deployments must review passkey counters and configure `WEBAUTHN_ORIGIN` before upgrading.
- **UTC Timestamps**: Use timezone-aware UTC values. Existing PostgreSQL deployments must follow the UTC migration instructions before starting this version.
- **Frontend**: Pin Vue to 3.5.39.

### Fixed
- **Package Build**: Configure Python package discovery and modern license metadata.
- **Kubernetes Example**: Remove the hard-coded database connection from the deployment manifest.

## [0.3.6] - 2026-11-10

### Fixed
- **Passkey Site Identity**: Clarified the service name supplied during passkey registration and added Open Graph site metadata to the home and login pages.
- **Apple Touch Icon**: Added a dedicated 180 × 180 icon for Apple devices.

## [0.3.5] - 2026-11-10

### Fixed
- **Authentik SSO Redirect & Callback Gateway**: Fixed third-party login navigation from static `/` to the dedicated `/outpost.goauthentik.io/start?rd=/api/auth/sso/callback` initiation pipeline.
- **SSO Callback & Session Issuance**: Added backend `/api/auth/sso/callback` handler extracting authenticated identity from Authentik, automatically mapping the administrator identity, issuing local sessions, and safely landing users onto the main dashboard without looping.

## [0.3.4] - 2026-11-10

### Added
- **Clean URL Routing**: Removed `.html` suffix across all routes and UI navigation. Direct access to `/login` serves authentication portal; legacy requests to `/login.html` and `/index.html` permanently 301-redirect to clean endpoints.
- **Passkey Hard Quota (5 Max)**: Strict enforcement allowing a maximum of 5 Passkeys per user with detailed audits on credential name, creation timestamp, and last verification time.
- **Self-Service Third-Party SSO Binding/Unbinding**: Users can bind or unbind Authentik SSO from their security center with anti-lockout prevention (prohibits unbinding if no password and no passkeys exist).

### Changed
- **Unified Single-Page Login**: Removed tabbed navigation (`账号密码` / `通行密钥` / `新用户注册`). Password authentication forms the primary card, with Passkey and Authentik SSO neatly displayed below as dedicated one-click option cards.
- **Closed Public Registration**: Completely closed self-registration endpoints (`POST /api/auth/register` returns 403 Forbidden). Accounts are managed and provisioned exclusively via administrator dashboard.

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
