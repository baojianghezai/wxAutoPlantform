# Flask 服务文档

> 文件：`自动化脚本合集/server/app.py`（端口 5001）。n8n ↔ 本地脚本/前端的桥接层。
> 依赖：`server/requirements.txt`（flask / flask-cors / requests）。
> 启动：`python server/app.py`，或双击 `启动服务.bat`。

## 1. 端点一览

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/waitUrl` | POST | 登记 n8n Wait 节点回调 URL（存 `server/state.json`） |
| `/api/run` | GET/POST | 触发爬虫 pipeline（后台线程，防重入），结束后回调 waitUrl |
| `/api/articles` | GET | 返回 `unified_articles.json` 原文 |
| `/api/templates` | GET | 展开 `templates/selector_config.json` 为扁平模板列表 |
| `/api/submit` | POST | `{article_id, template_id}` 抓原文 HTML → POST 到 waitUrl |
| `/api/publish` | POST | n8n 回调：渲染契约 JSON → render_article → push_to_draft |
| `/` 与静态资源 | GET | 托管 `wxcheck/dist`（存在时） |

全局：开启 CORS；统一 JSON 错误响应（`/api/` 不裸抛 HTML 500）。

## 2. 状态文件 `server/state.json`

单键状态，`_load_state()` / `_save_state()` 读写：

```json
{
  "waitUrl": "http://127.0.0.1:9000/wait",
  "saved_at": "2026-08-01 11:35:10"
}
```

- `waitUrl`：最近一次由 n8n 登记的 Wait 节点回调地址（两个 Wait 节点先后覆盖登记）。
- `saved_at`：登记时间。

## 3. 各端点详解

### POST /api/waitUrl（`app.py:86`）

```json
请求: {"url": "https://<n8n>/webhook-waiting/<uuid>"}
成功: {"code": 0}
失败: {"code":1,"msg":"missing url"}（400，url 为空/缺失）
```

行为：写 `state["waitUrl"]` 与 `state["saved_at"]`，落盘 `state.json`。

### GET|POST /api/run（`app.py:124`）

- 通过 `_pipeline_lock`（非阻塞 acquire）防重入：已被占用 → `{"code":1,"msg":"pipeline already running"}`。
- 否则开后台线程 `_pipeline_worker`，立即返回 `202 {"code":0,"msg":"pipeline started"}`。
- `_pipeline_worker`（`app.py:101`）：
  1. 调 `pipeline.run_all(log_fn)`（详见下），结果 `{code,msg,stats}`。
  2. 读 `state["waitUrl"]`，若存在则 `requests.post(wait, json={code,msg,stats})` 唤醒 n8n；无则仅记日志。

### GET /api/articles（`app.py:135`）

读 `crawl4ai/scripts/xinjiang_output/unified_articles.json` 返回，并为缺失 `source_category` 的文章兜底补齐（web→recruitment、wechat→other）。
文件不存在 → 404；解析失败 → 500。

返回 JSON 顶层含 `categories`（分类 id→label 列表），每篇文章带 `source_category`（recruitment/agriculture/other），由爬虫/合并脚本在代码层完成分类，前端仅按该字段分组渲染。

### GET /api/templates（`app.py:150`）

读 `templates/selector_config.json`，把每个 `content_types` 块展开成扁平列表，并附带模板 HTML 的 `body` 预览（截取前 2000 字符）与分类信息：

```json
{"code": 0,
 "categories": [{"id": "recruitment", "label": "招聘类"}, {"id": "agriculture", "label": "农业类"}, {"id": "other", "label": "其他"}],
 "templates": [
  {
    "id": "zhaopin1",
    "name": "春季招聘（清新蓝）",
    "content_type": "job_list",
    "content_type_label": "招聘岗位",
    "category": "recruitment",
    "category_label": "招聘类",
    "style": "blue",
    "description": "...",
    "previewHtml": "<body 内前 2000 字符>",
    "previewImage": "/api/tpl-preview/zhaopin1.png"
  }
]}
```

`category`/`category_label` 来自模板配置或所属 content_types 块的 `category` 字段（若配置了）。

### POST /api/submit（`app.py:184`）

流程：
1. 校验 `{article_id, template_id}` 均存在，否则 400。
2. 读 `state["waitUrl"]`，无则 `{"code":1,"msg":"no waitUrl registered"}`。
3. 从 `unified_articles.json` 找 `article_id`，找不到 404。
4. `fetch_html.fetch(art.url)` 抓原文正文 HTML（失败 502）。
5. 组装 payload 并 `requests.post(wait, json=payload)`：

```json
{
  "article_id": "web_8201fbd9",
  "title": "文章标题",
  "url": "原文链接",
  "html": "正文 HTML 片段",
  "template_id": "zhaopin1",
  "template_category": "recruitment",
  "template_category_label": "招聘类",
  "template_category_code": 1
}
```

`template_category_code` 为模板分类数字映射（1=招聘类、2=农业类、0=其他），由 Flask 按 `template_id` 查 `selector_config.json` 的 `categories.code` 生成，n8n 可按此分支。

6. POST 失败 → 502；成功 → `{"code":0,"msg":"submitted ... to waitUrl"}`。

### POST /api/publish（`app.py:227`）

请求体 = 大模型输出的结构化 JSON（`content_type/title/digest/sections` 等）。
行为：
1. `renderers.render_article(data)` → 渲染成公众号 HTML（选模板逻辑见 `docs/03-模板分类器文档.md`）。
2. `publish.push_to_draft(title, html, digest)` → 推微信草稿箱，返回 `media_id`。
3. 成功 `{"code":0,"media_id":"..."}`；任何异常 → 500 `{"code":1,"msg":...}`。

### 前端静态托管（`app.py:246`）

`/` 与 `<path:path>` 兜底路由：若 `wxcheck/dist` 存在则 `send_from_directory`，否则 404 提示先 build 或用 vite dev。`/api/*` 由上方具体路由优先匹配。

## 4. 模块协作

### server/pipeline.py —— 爬虫流水线

`run_all(log_fn) -> {"code":0|1, "msg", "stats"}`，5 步：

1. **task1_index.py**：抓公众号 RSS 信源 → `review/index.json`；先备份 `index.backup.json`，若新产出 0 条且备份非空则还原（防 RSS 不可达清空信源）。
2. **分方向爬虫**：`crawl4ai/scripts/xinjiang_directional/crawler.py --config config_*.json`，对每个 config 跑子进程（单方向失败不中断，记 `failed_directions`；超时 900s）。
3. **merge_summary.py**：合并各方向输出。
4. **adapter_task1.py**：`review/index.json` → 统一 articles 契约。
5. **combine.py**：web + wechat 合并去重 → `xinjiang_output/unified_articles.json`。

说明：
- 爬虫依赖 crawl4ai，`_find_crawl_python()` 按候选顺序探测解释器（`python` / `py -3.13` / `py -3` / 当前解释器）。
- 日志写 `server/pipeline.log`，同时转发给 `log_fn`。

### server/fetch_html.py —— 抓原文正文

`fetch(url) -> str`（失败抛 RuntimeError 带 url）：

- 微信链接（`mp.weixin.qq.com`）：提取 `id="js_content"` div 的 innerHTML（标签配平）。
- 其他站：带 UA 抓取，依次试 `<article>`、正文容器（id/class 含 article/content/main/post/entry/text/body 的 div，>200 字符才接受），兜底返回整个 `<body>`。

### publish/ —— 微信草稿箱发布

`push_to_draft(title, content_html, author, digest) -> media_id`（仅标准库 urllib）：

流程：access_token → 尾图预上传为 mmbiz URL 并挪到最后一个 `</section>` 内 → 清洗正文（data-src→src、data: 内联图上传统一为 mmbiz、mmbiz 强制 https）→ 封面上传取永久 media_id → `cgi-bin/draft/add`。

凭证：环境变量 `WECHAT_APPID`/`WECHAT_SECRET` 优先，回退 `config.json` 的 `wechat` 块。

## 5. 关键文件/常量

| 常量 | 路径 |
|------|------|
| `STATE_FILE` | `server/state.json` |
| `UNIFIED_JSON` | `crawl4ai/scripts/xinjiang_output/unified_articles.json` |
| `TEMPLATES_DIR` | `templates/` |
| `SELECTOR_CONFIG` | `templates/selector_config.json` |
| `FRONTEND_DIST` | `../wxcheck/dist` |

## 6. 常见问题

- **pipeline 找不到 crawl4ai**：`_find_crawl_python` 全部失败 → `/api/run` 返回 `{"code":1}`，提示安装 `python -m pip install crawl4ai && crawl4ai-setup`。
- **/api/publish 报 40164**：运行机公网 IP 不在公众号后台 IP 白名单。
- **回调 n8n 失败**：日志 `回调 waitUrl 失败 ...`，检查 n8n 是否可达、Wait 节点是否过期。
