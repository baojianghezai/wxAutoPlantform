# 开发文档 — 公众号招聘聚合发布系统（WorkBuddy）

> 本文档记录该项目目前已完成的功能，依据工作日志（`.workbuddy/memory/2026-07-16.md`、`2026-07-17.md`）与自动化执行记忆整理。

## 一、项目概述

围绕「青岛地区公众号招聘信息」搭建的**抓取 → 人工选稿 → 编辑 → 草稿箱发布**全链路自动化系统，运行在 WorkBuddy 定时任务上。每日 10:00 自动抓取并产出待审清单，人工选稿后，14:00 自动生成两篇草稿（原文稿 A + 自有岗位稿 B）并推入微信公众号草稿箱，人工审稿后一键发布。

数据源：本地 WeChat RSS 聚合器（`http://localhost:5000/api/rss/all`，generator: WeChat RSS），把订阅的公众号转成标准 RSS，自带 `mp.weixin.qq.com/s/...` 永久链接与完整文章 HTML，配图经 `/api/image?url=` 本地代理。解决了链接稳定、可抓全文/配图、无需账号凭证三大问题。

## 二、整体链路

```
RSS聚合器 ──10:00 Task1──▶ candidates/ 待审清单(review/index.html)
                                   │
                            人工选稿(pick_candidate.py)
                                   │ 选中的链接写入 selected_links.txt
                                   ▼
                         ──14:00 Task2──▶ 发文稿A(原文+尾图) + 发文稿B(岗位卡片)
                                   │
                            推入公众号草稿箱(draft/add)
                                   │
                            人工审稿 → 发布
```

## 三、已完成功能

### ~~1. RSS 招聘汇总（`build_rss.py` / `build_xlsx.py` / `build_xlsx_7d.py`）~~(已废除)
- ~~解析本地 WeChat RSS 聚合器，按「具体招聘单位」去重 + 跨账号别名合并（去重不能按通用词如"招聘公告"做最长公共子串，否则大量误合并）。~~
- ~~下载配图打包，生成 `青岛招聘公众号近7日文章汇总_RSS.xlsx`（含文章列表 + 说明表）。~~
- ~~流程固化为自包含提示词 `RSS招聘汇总_定时任务提示词.md`（RSS地址、6账号两级留存规则、动态7天窗口、过滤/去重规则、配图下载、Excel列、环境说明）。~~
- ~~已知局限：RSS 无阅读量字段（媒体/机构类≥1000 需人工复核）；正文极少内嵌可下载岗位表附件。~~

### 2. Task1 抓取与待审（`task1_fetch.py`，自动化 `1784166639022` 每天 10:00）
- 抓 RSS → 过滤 6 个账号近 7 天文章 → 按招聘单位去重 → 存 `candidates/Axx.html` 完整原文 + `Axx.meta.json`。
- **时效性过滤**：`extract_deadline()` 从标题+正文提取报名/招录截止时间（覆盖「截止X月X日 / 报名截止至 / 报名时间…至X月X日 / X月X日截止」；招满即止/长期有效返回 None 保留；无年份默认今年，取最晚日期）。截止时间早于当前则过滤，开关 `config.filter_expired`（默认 true）。
- 生成 `review/index.html` 待审清单（卡片含报名截止、账号分级、配图预览）；页头/汇总/status 透出「已过期过滤 N 篇」。
- 初始化/每日重置 `selected.json`（processed 或空→重置；当天候选含该 id→保留；否则作废），避免隔日残留选择喂给 Task2。
- 过期候选清理但保留已选中篇。

### 3. 人工选稿（`pick_candidate.py`）
- 人工运行 `python pick_candidate.py <候选id>` 写入选中（含无效 id 校验、title 回退匹配——因 Task1 每日重编号 Axx，按 title 仍能命中）。
- 选中的链接追加进 `selected_links.txt`（Task2 链接输入版）。
- **踩坑**：原名 `select.py` 与 Python 标准库 `select` 模块重名，导致 `import urllib.request` 触发 `import select` 加载本地文件而误退出；已改名修复。教训：工作区脚本切勿用标准库模块名命名。

### 4. Task2 编辑发布（`task2_publish.py`，自动化 `1784247680020` 每天 14:00）
仅用 Python 标准库实现，核心引擎。

**链接输入**：读 `selected_links.txt` 首个链接 → 实时抓 `mp.weixin.qq.com` 原文（失败时按 link 回退 candidates/ 缓存）→ 处理完 `consume_first_link()` 删除该行，保留其余。

**发文稿 A（企业官方招聘整理稿，新流程）**：
- 公众号文章**只作线索，不再照搬**。自动化（Task2 第 0 步）据线索企业名 WebSearch/WebFetch 去对应企业官网查招聘信息，提取结构化数据写入 `a_source.json`。
- 脚本读 `a_source.json` → 套 `templates/articleA/` 模板（企业官方招聘整理风格：公司简介/在招岗位/应聘方式/来源说明）渲染为发文稿A，文末带固定尾图；渲染后消费删除 `a_source.json`。
- 标题取 `a_source.json.article_title` 或「企业名 招聘信息」；来源说明注明「根据 XX 公众号线索整理，信息来源于企业官网，以官方为准」。
- 兼容回退：若无 `a_source.json`，仍走「选中文章原文 `js_content` 原封不动 + 尾图 + 单个顶层 `<section>` 包裹 + 剥微信哨兵标签」旧流程（标题原样使用）。

**发文稿 B（自有岗位稿）**：
- 读 `b_photos/<YYYY-MM-DD>/` 招聘截图 → 视觉提取岗位名+JD 写 `b_photos/extracted.json` → 套模板渲染岗位卡片；处理后截图移入 `b_photos/done/<YYYY-MM-DD>/`。
- **96 模板轮换**：`templates/96/` 顶层 + `real/` 全部 `*.html`（共 36 个：4 手写占位 + 32 真实 96 模板），按 `MANIFEST.json` 记录的 `last` 索引轮换，自动读取每个模板顶部 `<!-- ACCENT:#xxxxxx -->` 配色。
- **轮换已恢复**：`config.articleB_style_fixed` 已置空（此前被锁成 `tpl_refmimic.html` 导致 B 永远只用单一模板，已修复），B 现按 `MANIFEST.json` 在 4 手写占位 + 32 真实 96 模板间轮换；`tpl_refmimic.html` 仍在轮换池内。`render_job_cards_refstyle()` 为 refmimic 风格的卡片渲染器。
- 真实 96 模板无 `{{JOB_CARDS}}` 占位符时，抽其主题色/背景色/头图套到自有岗位卡片上，保证 B 永远是招聘内容。
- B 标题取 `config.articleB_title`（当前"企业招聘，就等你来"），与 A 标题分开，避免雷同。

**尾图处理（A/B 通用）**：
- `build_articleA/B` 都追加尾图；`embed_img_file()` 把尾图包成 `<section><img ...><!-- TAILIMG:xxx --></section>`。
- `_attach_tail_images()`：发布前把尾图 data: 内联图预上传为 mmbiz 地址并替换。
- `_place_tail_blocks()`：把尾图块作为**最后一个 `</section>` 内的最后子节点**（微信会丢弃「正文最后一个 `</section>` 闭合标签之后的兄弟节点」；对真实微信图文 A 多层嵌套尤其关键）。

**草稿箱发布（`publish_to_draft`）**：
- 用 `cgi-bin/draft/add`（**非**已废弃的 `freepublish/add`，后者对任何内容返 40066）。
- 自动取封面 `thumb_media_id`：`material/add_material?type=image` 永久素材（优先 `tail_images/` 首图，回退 `assets/fixed_tail.png`）。
- `_sanitize_for_publish()`：data-src→src 还原真实图、内联 data: 图上传为 mmbiz、mmbiz 图强制 https。
- `publish_mode=auto` 且配置微信 appid/secret 时自动推两篇到草稿箱；否则只产出 HTML 草稿标注手动粘贴。
- `mediaA/mediaB` 持久化到 `task2_status.json`。

### 5. 96 微信模板爬虫（`crawl_96.py` / `probe_96.py` / `discover_96.py`）
- `crawl_96.py`：封装 96 编辑器 `/indexajax/tplinfo`（文章模板）、`/indexajax/styleinfo`（文本样式）接口（POST + X-Requested-With + Referer + Cookie），支持 `--ids/--style-ids/--range`，输出到 `templates/96/real/`，自动带 `<!-- ACCENT -->`。用户带登录 cookie 一键灌入真实 96 模板，自动并入轮换。
- 用用户提供的登录 cookie（User_id=202642963）成功抓取 **32 个真实 96 模板**（id 24960~24991），0 失败。
- `probe_96.py`（按 id 实测）、`discover_96.py`（画廊解析）供后续"再爬更多"使用。
- 结论：96 模板 HTML 接口匿名请求返回「内容获取失败」，必须登录态 cookie 才能拿到真实 HTML。

### 6. 定时任务自动化
- **Task1** `automation-1784166639022`（每天 10:00）：RSS 抓取 → 过滤/去重 → 待审清单。`validUntil` 2026-12-31。
- **Task2** `automation-1784247680020`（每天 14:00）：链接输入 → 双稿生成 → 草稿箱推送 → 写任务 memory。`validUntil` 2026-12-31。
- 形成「10:00 抓取待审 → 人工选稿 → 14:00 编辑发布」闭环。

## 四、关键技术结论与踩坑（已固化）

| # | 结论 |
|---|------|
| 1 | 草稿发布用 `cgi-bin/draft/add`；`freepublish/add` 已废弃，对任何内容返 40066。 |
| 2 | `draft/add` 必填封面 `thumb_media_id`，且必须是永久素材（`material/add_material`），非 uploadimg 临时 URL。 |
| 3 | 正文图片 URL 必须来自 `media/uploadimg`（mmbiz 域）；外部图被"过滤"而非报错。 |
| 4 | 微信会丢弃「正文最后一个 `</section>` 之后的兄弟节点」——尾图必须在该 section 之内。 |
| 5 | 微信编辑器导入只认首个顶层块 → 正文须包成单个顶层 `<section>`，否则编辑时只剩标题+首图。 |
| 6 | `draft/add` 标题实测可存 ≥32 字（"≤32字硬限制"判断已作废），原样标题即可。 |
| 7 | 取 access_token 报 40164 = IP 白名单拦截，需把出网 IP（`182.33.26.203`）加入公众号后台 IP 白名单。 |
| 8 | 工作区脚本切勿用标准库模块名命名（`select.py` 踩坑）。 |
| 9 | `draft/batchget` 真实字段是 `item`（非 `item_list`）；`draft/get` 内容在 `news_item[0].content`。 |

## 五、目录结构

```
config.json                     全局配置（RSS/task2/wechat）
task1_fetch.py                  Task1：抓取+过滤+待审
pick_candidate.py               人工选稿
task2_publish.py                Task2：双稿生成+草稿箱发布（核心引擎）
build_rss.py / build_xlsx*.py   RSS 汇总与 Excel 生成
crawl_96.py / probe_96.py / discover_96.py   96 模板爬虫
selected_links.txt              Task2 输入：人工粘贴的微信文章链接
selected.json                   Task1 选稿记录
candidates/                     Axx.html 原文 + Axx.meta.json
review/index.html               待审清单
templates/96/                   96 模板（顶层手写 + real/ 真实爬取）
tail_images/                    A 文末尾图（mingshuo.jpg）
b_photos/<日期>/                 B 招聘截图（按天）；done/ 已处理
drafts/                         生成的 articleA.html / articleB.html
task1_status.json / task2_status.json   运行状态
RSS招聘汇总_定时任务提示词.md      RSS 汇总自包含提示词
```

## 六、配置说明（`config.json`）
- `rss`：RSS 地址、账号分级（两级留存）、天数窗口。
- `filter_expired`：时效性过滤开关（默认 true）。
- `task2`：`tail_images_dir`/`b_photos_dir`/`b_photos_done_dir`/`drafts_dir`/`templates_96_dir`/`templates/articleA`(`articleA_templates_dir`)/`a_source`/`articleB_title`/`articleB_style_fixed`(已置空→B轮换)/`publish_mode`（auto|html）。
- `wechat`：`appid`/`secret`（已配置测试号 `wxd676e5b7f48d1136`，IP 白名单已生效）。

## 七、待办与已知局限
- articleA 新流程为「线索→官网→模板整理」，内容来自企业官网而非公众号原文；仅当 `a_source.json` 缺失走回退旧流程时，才可能带入公众号原文中的微信独有组件（音视频/小程序卡片），换号重发可能丢失，选稿时留意。
- 运行环境出网 IP 可能漂移，若再报 40164 需把新 IP 加入白名单（或改 OAuth 方案）。
- 真实固定尾图已由用户提供（`tail_images/mingshuo.jpg`）。
- 96 模板持续扩充可随时用 `crawl_96.py` 带 cookie 灌入。
