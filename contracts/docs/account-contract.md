# 账号契约扩展（A3）

依据：`../../spec/docs/design-auth-v0.1.md`。本次仅修改公共契约并补充本文档，不包含实现。

| 操作 | 行为与响应 | 鉴权 |
| --- | --- | --- |
| 新增 `GET /api/v1/me` | 200 返回 `MeResponse`：脱敏邮箱、昵称、头像种子、集数、账号创建时间、`is_new`；无有效会话返回 401 | `ParentSession`，或浏览器 `ParentSessionCookie` |
| 新增 `PATCH /api/v1/me` | 请求 `{nickname}`；200 返回更新后的 `MeResponse`；401 无有效会话；422 昵称校验失败 | `ParentSession`，或浏览器 `ParentSessionCookie` |
| 新增 `POST /api/v1/auth/logout` | 撤销当前会话并清 Cookie；始终 204，无 body；无会话、已过期或重复退出也成功，无需幂等键 | `security: []` |
| 扩展 `POST /api/v1/auth/email/verify` | 原响应增加 `account: {email_masked, nickname, avatar_seed, is_new}` 和 `Set-Cookie` | 原鉴权及幂等要求不变 |

昵称为 2–12 个字符，允许中英文/数字，不允许空白开头结尾、连续空白或纯符号；允许昵称重复。长度用 `minLength`/`maxLength` 表达，完整字符规则写在 description 中。422 使用独立的 `NicknameValidationError`（`INVALID_NICKNAME`），沿用 `{error:{code,message,retryable,request_id}}` 外形，不修改原 `ErrorCode` 枚举和 HTTP 映射。

邮箱脱敏：本地部分保留前 3 位（不足 3 位保留 1 位），其余用 `***`，域名完整保留，如 `dzq***@gmail.com`、`a***@example.com`。

verify 的 `account.is_new=true` 表示本次验证新建了账号，供前端进入欢迎页；已有账号为 false。`MeResponse.is_new` 对应当前会话的该次验证结果，读取资料或修改昵称不改变它。

## 兼容性

原有 12 个 path、14 个操作保留，68 个 schema 内容完全不变；新增后共 14 个 path、17 个操作、75 个 schema。除 verify 成功响应的增量扩展外，原操作定义不变。

原 `Session` 设置了 `additionalProperties: false`，且同时用于儿童会话。因此新增 `EmailVerifyResponse`，保留原 `token`、`expires_at` 的引用、必填性和语义，仅增加可选的 `account`。不以 `allOf: [Session, ...]` 扩展封闭对象，避免新字段被拒绝，也不向儿童会话注入账号资料。旧版响应仍符合新 schema；扩展服务返回账号摘要时，原客户端可继续读取原字段。使用旧版封闭 schema 严格校验完整响应的客户端须更新契约才能接受新字段，这是增加响应字段的兼容边界。

新增 `ParentSessionCookie` 表达浏览器凭据；保留原 `ParentSession` Bearer 定义，新 `/me` 操作显式声明两种认证方式任选其一。既有接口的鉴权声明不变。

设计文档提出的 30 天会话、滑动续期及 localStorage 兜底未纳入本次契约：硬要求优先，既有父会话至多 24h、token 仅在前端内存且不写 URL/localStorage 等语义保持不变。

## Cookie 与 token 并存

verify 成功响应补充：

```http
Set-Cookie: tk_session=…; HttpOnly; Secure; SameSite=Lax; Max-Age=…; Path=/
```

`Max-Age` 是当前会话剩余有效秒数，与 `expires_at` 一致。浏览器通过 HttpOnly Cookie 携带会话；响应体 `token` 继续供非浏览器客户端使用 `Authorization: Bearer …`，保持现有调用方式。两者代表同类父会话，不改变权限或有效期。Secure Cookie 需要 HTTPS；当前契约保留的一期 HTTP server 地址不会因此自动获得浏览器 Cookie 支持，部署接入 HTTPS 后才能使用该方式。

logout 撤销当前凭据对应的会话，并返回 `tk_session=; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Path=/` 清除 Cookie。

## 校验

- `python3 -c "import yaml,sys; yaml.safe_load(open('openapi.yaml'))"`：通过。
- 与提交前契约做结构比对：原 68 个 schema、原参数、原错误响应、原安全方案完全相同；原操作仅允许 verify 的增量扩展，通过。
- 本地 `$ref` 全部可解析，operationId 无重复；`git diff --check` 通过。
- 仓库未提供 Spectral/Redocly 配置或脚本；按 README 执行 `uv tool run openapi-spec-validator openapi.yaml`（缓存和工具目录设为 `/tmp` 下可写目录）：`openapi.yaml: OK`。
