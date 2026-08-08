# n8n 对接说明

> 本地 Flask 服务：`自动化脚本合集/server/app.py`，默认 `http://localhost:5001`
> （5000 已被目标机 Docker 上的 RSS 服务占用）。
> 启动：双击项目根目录 `启动服务.bat`（首次自动建 `.venv` 装依赖）；或手动 `python server/app.py`。

## 完整流程时序

```
n8n 定时触发
  → ① POST /api/waitUrl        登记 wait 节点回调地址
  → ② GET  /api/run            触发爬虫 pipeline（立即返回 202，后台跑）
  → (n8n Wait 节点挂起，等 Flask 回调)
  → Flask 爬虫结束 → POST {waitUrl}   唤醒 n8n
  → ③ n8n 调钉钉 API 发审核通知
  → 运营打开前端 http://localhost:5173 选文章 + 模板
  → 前端 POST /api/submit → Flask 抓原文 HTML → POST {waitUrl}（带 html）
  → ④ n8n 收到 HTML，去标签 → 大模型改写成结构化 JSON
  → ⑤ n8n POST /api/publish（结构化 JSON）→ 渲染模板 → 推微信草稿箱
```

## 各节点契约

### ① POST /api/waitUrl

请求：
```json
{"url": "https://<n8n>/webhook-waiting/xxxxx"}
```
响应：`{"code": 0}`。URL 落盘 `server/state.json`，重启不丢。

### ② GET /api/run

响应（立即返回）：`{"code": 0, "msg": "pipeline started"}`
运行中重复调用：`{"code": 1, "msg": "pipeline already running"}`

**爬虫结束后 Flask 回调 waitUrl 的 payload：**
```json
{
  "code": 0,
  "msg": "pipeline done",
  "stats": {"web_total": 40, "wechat_total": 34, "total": 74, "failed_directions": []}
}
```

### ③ 前端 → /api/submit（前端自动调，n8n 无需关心）

前端确认推送后，Flask 抓原文 HTML 并回调 waitUrl：

**Flask → waitUrl 的 payload（n8n Wait 节点收到的数据）：**
```json
{
  "article_id": "web_8201fbd9",
  "title": "文章标题",
  "url": "原文链接",
  "html": "原文正文 HTML（已提取正文区域）",
  "template_id": "zhaopin1",
  "template_category": "recruitment",
  "template_category_label": "招聘类",
  "template_category_code": 1,
  "target_account": "zhaopin",
  "target_account_name": "青岛招聘号"
}
```

**模板分类映射表**（`template_category_code`，定义见 `templates/selector_config.json` 的 `categories`）：

| code | category | label |
|------|----------|-------|
| 1    | recruitment | 招聘类 |
| 2    | agriculture | 农业类 |
| 0    | other / 未命中 | 其他 |

> `template_category_code` 由 Flask 按 `template_id` 查模板归属分类生成，n8n 后续节点可直接按此数字做分支（如选择文案语气/封面）。

**目标公众号**：`target_account`/`target_account_name` 由前端在预览页选择、经 `/api/submit` 传入。n8n 在步骤⑤ POST `/api/publish` 时需**原样透传 `target_account`**，Flask 将用该账号的 appid/secret 推送草稿。账号凭证配置在项目根 `config.json` 的 `wechat.accounts`（数组，含 id/name/appid/secret）。

### ④ n8n 大模型处理（prompt 约束）

对 `html` 去标签后交给大模型，**要求大模型输出严格 JSON**：

```json
{
  "content_type": "job_list | solar_term | 其他",
  "template_id": "可选，显式指定模板（zhaopin1/zhaopin2/xiaoshu）",
  "title": "公众号文章标题",
  "digest": "摘要，可选",
  "sections": [
    {"type": "hero", "title": "...", "subtitle": "..."},
    {"type": "cards", "items": [{"title": "...", "fields": {"键": "值"}, "tags": ["..."], "description": "..."}]},
    {"type": "key_points", "title": "...", "points": ["...", "..."]},
    {"type": "paragraph", "heading": "可选", "text": "..."},
    {"type": "image", "url": "...", "caption": "可选"}
  ]
}
```

- `content_type` 决定默认模板与渲染器：`job_list`（招聘岗位）、`solar_term`（节气时令），其他值走兜底渲染。
- sections 的 type 目前支持：`hero` / `cards` / `key_points` / `paragraph` / `image`，顺序任意。
- **`template_id` 必须原样透传**：Wait② payload 中若带 `template_id`（前端运营选的模板），大模型输出必须原样带上、不得省略或修改；仅当输入无 `template_id` 时才省略（由系统按 content_type 默认模板兜底）。—— 完整字段规则见 `docs/04-大模型字段说明书.md`。

### ⑤ POST /api/publish

请求体 = 大模型输出的结构化 JSON（原样 POST 即可），若 Wait② 收到过 `target_account` 需一并带上：

```json
{
  "content_type": "job_list",
  "template_id": "zhaopin1",
  "title": "文章标题",
  "digest": "摘要",
  "sections": [...],
  "target_account": "zhaopin"
}
```

`target_account` 缺省时兜底顺序：前端最近一次 `/api/submit` 选定的账号（存 `server/state.json` 的 `publish_account`）→ 旧式单账号（config.json `wechat.appid/secret` 或环境变量）。n8n 即使忘记透传 `target_account`，也会发到前端刚选的账号。

成功响应：`{"code": 0, "media_id": "..."}`
失败响应：`{"code": 1, "msg": "..."}`（HTTP 500）

**注意**：推草稿箱要求运行机器的公网 IP 在**目标公众号**后台的 IP 白名单内，否则报 `errcode 40164`。凭证读取逻辑：`/api/publish` → `publish/wechat_draft.py`，按 `target_account` 查 `config.json` 的 `wechat.accounts`。

## 前端接口（ vite dev 已配置 /api 代理）

| 接口 | 用途 |
|------|------|
| `GET /api/articles` | 文章卡片列表（web + wechat 合并 feed） |
| `GET /api/templates` | 模板列表（含 previewHtml 预览） |
| `POST /api/submit` | 选定文章+模板，触发原文 HTML 回调 n8n |
