# 项目协作规范

本仓库是 sub-egress 订阅聚合与出站调度服务：`backend/app/` 为 FastAPI 后端，`frontend/` 为静态前端，`backend/tests/` 为测试，`k8s/` 为部署示例。

- 遵循用户要求与上级目录规则；保持最小改动，保留已有注释和文档。重大改动先只读调查、提交可复查方案并等待明确确认；破坏性操作先确认。
- 修改前阅读对应规则：开发和验证见 [.agents/rules/development.md](.agents/rules/development.md)，认证、凭据或配置见 [security.md](.agents/rules/security.md)，版本或发布见 [release.md](.agents/rules/release.md)。这些文件由本入口引用，不假定工具会自动加载。
- 依据实际改动选择检查，报告执行结果和未覆盖范围。需要项目验证流程时使用 `.agents/skills/sub-egress-validation/SKILL.md`。
- 发现明文凭据、可疑数据或线上故障时先核实并向用户说明；不要在日志、提交或回复中输出秘密。线上数据库及入口变更按影响范围单独评估。
- 报告实际差异、行为变化、验证结果和未解决问题；不要把失败或未执行的检查说成通过。
