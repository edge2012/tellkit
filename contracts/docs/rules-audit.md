# W21a 规则版本与完成审计

`rules_fingerprint.py` 是规范算法，`worker/scripts/sync_rules_contract.py --write` 将它打包到 `worker/app`，同时生成两个期望指纹文本。content 与 worker 镜像使用同一个 app 模块；API 将已审核的期望值 embed 到二进制，不从请求或 content 动态学习。CI/发布前运行不带 `--write` 的命令检查同步。选择 contracts 规范算法，避免跨镜像各自维护算法；源码模块整体参与 hash，比手工列出函数更保守，注释变化也需要同步发布。

SHA256 输入是固定顺序的 `[相对路径, UTF-8 源码]` JSON，紧凑分隔符、非 ASCII 不转义、CRLF 转 LF。覆盖 W16/W17 的校验源码、阈值/允许集合及依赖模块，以及 B3 明暗实现/调用源码。B3 没有独立的分镜 validator，指纹保证实现版本一致，不声称通过审计就证明最终画面的美术质量。规则内容不变。

`POST /storyboard` 成功响应在原分镜对象旁新增 `rules_fingerprint: <64 lowercase hex>`，这是传输元数据，不属于保存的 storyboard schema。worker 先比较再剥离元数据并进行本地强校验。`GET /healthz` 返回启动固定记录指纹、`started_at`、`rules_source_mtime` 和 `rules_source_changed`。mtime 覆盖 content/worker Python 源码，响应时不重新计算运行指纹。

`POST /internal/worker/v1/jobs/{job_id}/complete` 必须新增：

```json
{"storyboard_audit":{"verdict":"pass","violations":[],"rules_fingerprint":"<64 lowercase hex>","audited_at":"2026-11-13T12:00:00Z"}}
```

worker 在原 prompt 上下文中复验最终分镜后生成审计。API 要求全部字段、有效时间、pass、空 violations、匹配的期望指纹；否则有效租约下任务及版本置 failed，HTTP 422 只返回中文 message。拒绝原因保存到 episode_version.storyboard_failure_reason，并通过 Job.reason 返回。成功审计保存到 episode_version.storyboard_audit；审计参与完成请求幂等摘要，修改审计重放会冲突。旧 worker 不兼容，不能绕过门禁。

先执行数据库迁移 `00015_storyboard_audit.sql`，同步 content/worker/API 发布版本集合，再更新服务；本任务未部署。自检运行方法见 worker W21 报告。
