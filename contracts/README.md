# Tellkit 公共 API 契约

版本 **0.2.0**，OpenAPI **3.1.0**，**2026-11-11 增量对齐 A16**（原 0.1.0 于 2026-11-09 冻结）。接口依据为 [架构 §6](../src/docs/architecture-v2.0.md#6-接口契约) 及后续任务契约，§3 仅辅助字段命名；任务明确要求的端口、UUID 和保留错误码优先。仅覆盖 27 个公共操作（24 个 path），不包含 worker/service 接口。

## 兼容策略

手写 [openapi.yaml](openapi.yaml) 是契约交付物，[errors.md](errors.md) 与 `ErrorCode` 枚举同步维护。修改先更新契约版本并做兼容性检查，再更新实现；破坏性变更另开主版本，不直接破坏现有 v1 客户端。冻结前必须解决下列未决项；不得把草案假设当作已冻结行为。

兼容性增量提升次版本号。本次 A17 以运行时 `api/internal/httpapi/contract.json` 和路由实现逐项人工核对 A16 遗漏：新增发布、撤回、举报及我的集列表路径，补充广场 scope、可选展示字段和错误码；原请求与响应形状保持兼容，因此从 0.1.0 升至 0.2.0。

## 使用

服务地址仅为 `http://192.0.2.1:8099`（一期 IP 直连）。使用支持 OpenAPI 3.1 的预览器或客户端生成器直接加载 YAML。实现测试需对请求、成功/错误响应双向校验，并检查操作与实际路由一致；不得由实现反向生成或覆盖此文件。

每个操作显式声明鉴权；匿名选项仍受 official/scope 条件约束。声明 `x-idempotency: required` 的写请求带 UUID `Idempotency-Key`；同键不同规范化 body 为 409，同键处理中为 409 并带 `Retry-After`。发布、撤回、举报使用 `x-idempotency: state-based`，无需幂等键，分别按当前发布版本、撤回状态、举报账号去重，不缓存 HTTP 响应重放；账号接口按各操作说明执行。GET 天然幂等，播放地址重新签发且 `Cache-Control: no-store`。分页采用 `limit/cursor/next_cursor`，默认 20、上限 50，账号所属列表游标基于 `(created_at,id)`；广场官方作品在前，社区作品按 `(published_at,id)` 倒序。时间为 UTC `date-time`，持续时间仍使用秒/毫秒数值。

## 待冻结项

草案阶段遗留 5 项，**已于 2026-11-09 全部落进 yaml 并复跑校验（v0.1.0 冻结）**：

1. `challenge_id` → **UUID**。它不是第三方 IdP 发的，是我们自己的挑战表主键，不存在兼容问题。
2. 验证码过期 → 新增错误码 **`CHALLENGE_EXPIRED`**，HTTP 410。
3. 广场「看更多」→ 增加可选参数 `group_key`（缺省为整页重新拉全部组）；`limit` 优先级：**显式 limit > 2×columns**；`items` 形状统一为 `{id,title}`。
4. 详情无已发布版 → `summary: null` 且 `playable: false`，不省略字段（前端不用做二选一判断）。
5. 三个错误码对外映射：`WORKSPACE_BUSY` → **409**，`CONTENT_REJECTED` → **422**，`LEASE_LOST` → **仅内部，不出现在业务响应**。

## 校验

在仓库根目录运行（需要 PyYAML、uv；首次运行校验器可能需要访问包索引）：

```sh
python -c "import yaml,sys;yaml.safe_load(open('contracts/openapi.yaml'))"
uv tool run openapi-spec-validator contracts/openapi.yaml
```

本次检查（2026-11-11，A17）：每处手工补丁后 `yaml.safe_load` 均通过；最终为 24 个 path、27 个公共操作、85 个 schema。paths 与运行时 `contract.json` 完全一致，schemas 集合覆盖运行时；A16 新增数据结构逐项一致，382 个引用均可解析，31 个错误码与 errors.md 完全一致。在 contracts 目录运行 `uv tool run openapi-spec-validator openapi.yaml` → **`openapi.yaml: OK`**（沙箱内将 uv 缓存及工具目录设于 `/tmp`）。

引用、响应与错误码一致性可用以下只读脚本复核：

```sh
python - <<'PY'
import re, yaml
from pathlib import Path
spec = yaml.safe_load(Path('contracts/openapi.yaml').read_text())
refs = []
def walk(node):
    if isinstance(node, dict):
        if '$ref' in node:
            ref = node['$ref']; target = spec
            assert ref.startswith('#/'), ref
            for part in ref[2:].split('/'):
                target = target[part.replace('~1', '/').replace('~0', '~')]
            refs.append(ref)
        for value in node.values(): walk(value)
    elif isinstance(node, list):
        for value in node: walk(value)
walk(spec)
ops = [v for p in spec['paths'].values() for k,v in p.items()
       if k in {'get','post','put','patch','delete','head','options','trace'}]
assert len(ops) == 27 and all(o.get('responses') for o in ops)
codes = spec['components']['schemas']['ErrorCode']['enum']
rows = re.findall(r'^\| `([A-Z_]+)` \|', Path('contracts/errors.md').read_text(), re.M)
assert len(codes) == len(set(codes)) == len(rows) == len(set(rows))
assert set(codes) == set(rows), (set(codes)-set(rows), set(rows)-set(codes))
print(f'PASS: {len(refs)} refs resolved; {len(ops)} operations have responses; {len(codes)} error codes match errors.md exactly')
PY
```
