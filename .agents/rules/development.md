# 开发与验证

- 后端为 Python/FastAPI，前端为静态 HTML 和 Vue 组件；优先沿用现有结构，避免无关重构。
- Python 版本要求和项目版本以 `pyproject.toml` 为准；容器依赖来自 `backend/requirements.txt`。两者变化时核对一致性。
- 根据改动执行适用的 `PYTHONPATH=backend python -m pytest backend/tests -q`、`ruff check backend/app` 和语法检查；缺失依赖或历史失败时如实报告，不为绿灯掩盖问题。
- 涉及 API、认证、数据库、订阅生成或兼容性时，用覆盖实际行为的测试验证；不要添加仅复述实现的测试。
- 图像优先选择适合用途且兼容目标客户端的格式；大图可评估 JPEG XL 与回退格式的实际效果。保留 SVG 原始图标和 Apple touch icon 所需的 PNG，不因格式较新而强制替换。
- 不把本机绝对路径、账户信息和私有部署细节当作开源项目的通用要求。
