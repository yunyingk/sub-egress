---
name: sub-egress-validation
description: 验证 sub-egress 的代码、静态资源或发布前改动，选择与变更相关的检查并报告结果；不负责执行部署。
---

# sub-egress 改动验证

1. 查看实际 diff 和相关入口，识别后端、前端、认证、配置、版本或发布影响；不要假设未执行的检查已通过。
2. 后端改动优先运行 `PYTHONPATH=backend python -m pytest backend/tests -q` 和项目 CI 的 Ruff 检查；环境或既有问题造成失败时记录原因。涉及认证、订阅、数据库时检查现有测试是否覆盖实际行为。
3. 前端或静态资源改动验证资源路径和响应；需要时检查目标浏览器的实际行为。版本改动核对 `pyproject.toml`、README 与 changelog。
4. 汇报检查命令、结果、未覆盖项和风险。发布验证按 `.agents/rules/release.md` 执行；本技能本身不授予部署权限。
