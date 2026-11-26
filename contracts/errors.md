# 错误码（0.2.0，2026-11-11 对齐 A16）

统一响应为 `{error:{code,message,retryable,request_id}}`；门禁类额外包含顶层 `gate:{decision,reason_codes}`。`request_id` 为 UUID。不回显原文或供应商堆栈。

下表与 `components/schemas/ErrorCode/enum` 完全一致。HTTP 映射来自架构 §6 及已实现的账号、UGC 契约（`api/internal/httpapi/api.go` 的 `statuses`）；保留码不挂到业务路径。`retryable` 由服务端明确给出；示例值不构成所有场景的重试分类规则。

| 错误码 | HTTP | 语义 |
| --- | --- | --- |
| `INVALID_ARGUMENT` | 400 | 请求参数不合法 |
| `AUTH_REQUIRED` | 401 | 缺少有效鉴权 |
| `FORBIDDEN` | 403 | 当前会话无权执行此操作 |
| `NOT_FOUND` | 404 | 资源不存在；越租户也返回此码 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同幂等键对应不同规范化请求 |
| `REQUEST_IN_PROGRESS` | 409 | 同键请求处理中；返回 Retry-After |
| `QUOTA_EXCEEDED` | 402 | 额度不足 |
| `WORKSPACE_BUSY` | 409 | 该 workspace 已有 2 个活跃任务，稍后再提 |
| `ACTIVE_JOB` | 409 | 当前集存在活动任务 |
| `VERSION_CONFLICT` | 409 | 修改所依据的版本冲突 |
| `NOT_READY` | 409 | 指定播放版本未发布 |
| `MEDIA_EXPIRED` | 410 | 媒体已清理 |
| `CHALLENGE_EXPIRED` | 410 | 验证码或挑战已过期，需重新发送 |
| `MEDIA_UNAVAILABLE` | 503 | 媒体因其他故障不可用 |
| `GATE_GUIDE` | 422 | 门禁引导；附 gate.decision=guide |
| `GATE_REFUSE` | 422 | 门禁拒绝；附 gate.decision=refuse |
| `GATE_DOWN` | 503 | 门禁不可用；附 gate.decision=down |
| `CONTENT_REJECTED` | 422 | 生成内容未过输出审核，或发布时素材不满足要求、内容被 Gate 拒绝 |
| `DECLARATION_REQUIRED` | 422 | 发布声明缺失或不为 true |
| `CONTENT_NEEDS_REVIEW` | 422 | 发布审核返回 guide，或累计两次举报后禁止自行重新上架；审核结果可附 error.details.reason_codes |
| `PUBLISH_RATE_LIMITED` | 429 | 账号跨工作区当日发布已达三集，按 Asia/Shanghai 自然日统计；撤回或删除不返还名额 |
| `RATE_LIMITED` | 429 | 触发频控 |
| `DEPENDENCY_UNAVAILABLE` | 503 | 依赖不可用 |
| `INTERNAL` | 500 | 未预期的内部错误（含 panic）；retryable=false |
| `LEASE_LOST` | 内部 | 仅 worker↔api 间使用，**不出现在任何业务响应** |
| `INVALID_SCOPE` | 400 | 搜索 scope 不合法 |
| `ALREADY_COMPLETED` | 409 | 任务已完成，不能取消 |
| `INVALID_CODE` | 401 | 验证码无效 |
| `INVALID_CREDENTIALS` | 401 | 邮箱或密码凭据无效 |
| `ACCOUNT_EXISTS` | 409 | 账号已存在 |
| `PASSWORD_INVALID` | 422 | 密码不满足要求 |

`REQUEST_IN_PROGRESS` 必须附带 `Retry-After`。验证码过期使用 `CHALLENGE_EXPIRED`（410），与 `INVALID_CODE`（401）区分：前者是时间到了，后者是码错了。门禁 `reason_codes` 是规则版本输出，`NEEDS_CONTEXT` 仅为来源示例。
