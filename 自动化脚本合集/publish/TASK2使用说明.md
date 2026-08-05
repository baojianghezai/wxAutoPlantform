# Task2 编辑与发布服务 · 使用说明

> 本文档总结「青岛招聘公众号」自动化流水线中 **Task2（编辑发布）** 的完整能力、今上午跑通的关键结论与踩坑、目录职责、配置项与操作步骤，供后续运行/维护直接使用。
>
> 配套代码：`task2_publish.py`（仅依赖 Python 标准库，无第三方包）。

---

## 一、服务概述

Task2 把「人工选好的一篇招聘长文 + 一组招聘岗位截图」加工成 **两篇公众号图文草稿**，并推送到公众号草稿箱供人工审稿后发布。

- **发文稿 A（企业官方招聘整理稿）**：公众号文章**只作线索，不再照搬**。自动化先据线索企业去对应**企业官网**查招聘信息、写入 `a_source.json`，脚本再套 `templates/articleA/` 模板整理成「公司简介 / 在招岗位 / 应聘方式 / 来源说明」稿，文末追加 `tail_images/` 全部图片。无 `a_source.json` 时回退「原文照搬」旧流程。
- **发文稿 B（岗位稿）**：读取 `b_photos/extracted.json`（岗位信息，由视觉提取生成），套用 96 微信风格模板渲染成「招聘岗位卡片」，文末同样追加尾图。`articleB_style_fixed` 已置空，B 现于 `templates/96/`（4 手写占位 + 32 真实 96 模板，共 36 个）间**轮换**；`tpl_refmimic.html` 仍在轮换池内。

两条流水线产出 `drafts/articleA.html` 与 `drafts/articleB.html`，并（在配置凭证后）自动 `draft/add` 推入公众号草稿箱。

**与 Task1 的衔接**：Task1 每天 10:00 抓取近 7 日招聘文章、生成待审清单（写入 `selected.json`）。人工从清单里挑出一篇、把文章链接粘进 `selected_links.txt`；Task2 取该链接跑编辑发布。

---

## 二、今上午跑通的关键结论（核心知识点，务必保留）

这些是调通微信草稿箱发布时踩坑得到的结论，已固化进 `task2_publish.py`，后续不要回退。

### 1. 发布端点必须用 `draft/add`，不是 `freepublish/add`
- `cgi-bin/freepublish/add` 已废弃/被取代，**对任意内容（哪怕最小测试稿）都恒返 `40066 invalid url`**。这正是「连最小内容都 40066」的真正原因，与图片/外链无关。
- 正确端点：`cgi-bin/draft/add?access_token=...`（新增草稿）。发布到草稿箱后由人工在后台点「发布」。

### 2. `draft/add` 必填 `thumb_media_id`（封面）
- 图文消息**必须带封面 `thumb_media_id`**，且必须是**永久素材**的 `media_id`（`material/add_material?type=image` 返回），不能用 `media/uploadimg` 返回的一次性 URL。
- 缺失会直接报 `40066`。代码里 `_get_thumb_media_id()` 优先用 `tail_images/` 首图、回退 `assets/fixed_tail.png`。

### 3. 尾图必须插到「最后一个 `</section>` 之前」
- `draft/add` 会把正文末尾那串 `</section></section>…` **闭合标签之后**的「兄弟节点」当文末垃圾丢弃。尾图若甩在文末闭合标签**外面**会被清掉。
- 修复：代码 `_place_tail_blocks()` 把尾图块移到最后一个 `</section>` 之前（仍属正文内容树），入箱后可见。
- 微信会自动把上传图 `…/0?from=appmsg` **改写为 `…/640?from=appmsg`**，且会**剥掉 `<!-- TAILIMG -->` 注释**。校验尾图是否落库，用其独有内联样式 `margin:24px auto 0` 判定，不要靠 URL 或注释。

### 4. 正文图片 URL 必须来自 `media/uploadimg`（mmbiz 域）
- 内联 `data:image` 图（如尾图 base64）必须在发布前上传替换成 mmbiz 地址（`_attach_tail_images` + `_sanitize_for_publish` 已处理）。
- 微信懒加载：`data-src` 才是真实图，发布前需把 `data-src→src`（`_sanitize_for_publish` 已处理）。
- `http://mmbiz.qpic.cn` 会被拒，需替换成 `https://`（`_sanitize_for_publish` 已处理）。
- 外部图片 URL 会被「过滤」而非报错；`w3.org` 之类片段不会触发 40066——不必为它过度清洗。

### 5. 两篇标题要分开设置
- A 标题（新流程）取 `a_source.json.article_title` 或「企业名 招聘信息」；无 `a_source.json`（回退旧流程）时取原文标题。
- B 用 `config.task2.articleB_title`（当前为 `企业招聘，就等你来`）。
- **切勿**用 `A 标题 + 后缀` 给 B 命名——否则两篇标题雷同（今上午初版就犯了这个错，已修：`main()` 中 B 标题取自配置）。

### 6. 其它规则
- `title` ≤ 32 字、`digest`（摘要）≤ 128 字（代码已截断）。
- 账号类型：官方写「订阅号✔/服务号✔」；**接口测试号默认不在可调用列表**。本测试号 `你的测试号AppID` 实测 `draft/add` 可用（可能该号有发布权限）；若换号报权限错，需换认证服务号/订阅号或改 OAuth 方案。
- 取 `access_token` 受公众号 **IP 白名单**限制。运行环境出网 IP ≈ `182.33.26.203`，需加入公众号后台→开发→基本配置→IP 白名单，否则报 `40164`。

---

## 三、目录结构与文件职责

```
.
├── config.json                 # 全局配置（含 task2 块、wechat 块）
├── selected_links.txt          # 【输入】人工粘贴的待发布微信文章链接，每行一个
├── selected.json               # Task1 写入的待审清单（Task2 取链接时参考）
├── candidates/                 # Task1 抓取的候选文章原文缓存（按 link 回退匹配）
├── a_source.json               # 【输入·新流程】自动化据线索去官网查证后写入的企业招聘结构化数据（发文稿A数据源，脚本消费后删除）
├── tail_images/                # 【输入】A/B 文末追加的尾图（当前 mingshuo.jpg）
├── b_photos/                   # 【输入】招聘截图按天归档
│   ├── <YYYY-MM-DD>/           #     当日待处理截图（Task2 运行时读取）
│   ├── done/<YYYY-MM-DD>/      # 已处理截图（运行后自动移入）
│   └── extracted.json          # 【输入】视觉提取出的岗位信息（岗位稿B的数据源）
├── templates/96/               # 发文稿B 模板库（轮换）
│   ├── tpl_refmimic.html       #   轮换池内模板（仿「企业招聘，就等你来」蓝黄风格）
│   ├── tpl_blue/green/purple/red.html  # 手写占位模板（带 {{PAGE_TITLE}}/{{JOB_CARDS}}/{{FOOTER}}）
│   ├── real/                   #   真实96模板（需登录 cookie 爬虫灌入）
│   └── MANIFEST.json           # 轮换索引
├── templates/articleA/         # 发文稿A 模板库（企业官方招聘整理风格，带 {{COMPANY}}/{{INTRO}}/{{POSITIONS}}/{{APPLY}} 等占位符，按 MANIFEST 轮换）
├── assets/fixed_tail.png       # 封面回退图（无 tail_images 时使用）
├── drafts/                     # 【输出】articleA.html / articleB.html（成品草稿）
├── task2_publish.py            # 主程序（仅标准库）
├── task2_status.json           # 运行状态输出
├── crawl_96.py / probe_96.py / discover_96.py  # 96 模板抓取工具（需 cookie）
└── RSS招聘汇总_定时任务提示词.md  # Task1 提示词参考
```

---

## 四、配置说明（`config.json`）

```jsonc
{
  "selected_links_file": "selected_links.txt",   // 输入链接文件
  "candidates_dir": "candidates",                 // 原文缓存目录
  "task2": {
    "tail_images_dir": "tail_images",             // 尾图目录（A/B 文末追加）
    "b_photos_dir": "b_photos",                   // 招聘截图根目录（按天子目录）
    "b_photos_done_dir": "b_photos/done",         // 已处理截图归档
    "b_extracted": "b_photos/extracted.json",     // 岗位数据源
    "templates_96_dir": "templates/96",           // 发文稿B 模板库
    "articleB_template": "96wx_cards",            // 回退模板名（无模板库时使用）
    "articleB_title": "企业招聘，就等你来",         // 【B 标题】随改随生效
    "articleB_style_fixed": "",                  // 留空=B 走 templates/96/ 轮换（已修复"只用单一模板"问题）
    "articleA_templates_dir": "templates/articleA", // 发文稿A 模板目录（按 MANIFEST 轮换）
    "a_source": "a_source.json",                 // 新流程：企业官网结构化招聘数据（自动化写入，脚本消费后删除）
    "drafts_dir": "drafts",
    "normalize_image_urls": true,                 // 把本地代理图URL还原为真实 mmbiz
    "publish_mode": "auto"                         // "auto"=推草稿箱；"html"=仅出HTML
  },
  "wechat": {
    "appid": "你的测试号AppID",                      // 测试公众号 AppID
    "secret": "（已配置，不外露）"                  // AppSecret
  }
}
```

**常用调整**：
- 改 B 标题 → 改 `task2.articleB_title`。
- 换 B 版式 → 把 `task2.articleB_style_fixed` 指向其它模板，或留空启用 `templates/96/` 轮换。
- 发文稿A 新流程 → 自动化（Task2 第 0 步）据线索企业 WebSearch/WebFetch 官网写 `a_source.json`；脚本套 `templates/articleA/` 模板渲染（公司简介/在招岗位/应聘方式/来源说明）。无 `a_source.json` 时自动回退「原文照搬」。
- 仅想本地出 HTML、不推送 → `task2.publish_mode` 改为 `html`。

---

## 五、使用流程（操作步骤）

### 前置准备（人工）
1. 把要发布的文章链接粘进 `selected_links.txt`（一行一个；用完 Task2 会自动删掉已消费行）。
2. 把固定尾图放入 `tail_images/`（如 `mingshuo.jpg`）。
3. 把招聘截图放入 `b_photos/<当天>/`，并准备好 `b_photos/extracted.json`（岗位名+薪资+地点+JD+标签；可由视觉提取生成，schema 见 `b_photos/extracted.example.json`）。
4. 确认 `config.wechat` 已填且 `publish_mode=auto`；公众号 IP 白名单已含运行环境出网 IP。

### 运行
```bash
python task2_publish.py
```
或在 WorkBuddy 中触发对应的 Task2 自动化（每天 14:00，或手动触发）。

### 运行后
- 生成 `drafts/articleA.html`、`drafts/articleB.html`。
- 若凭证齐全（`auto`）→ 两篇推入公众号**草稿箱**，控制台/状态文件给出 `media_id`。
- 打开公众号后台→草稿箱→**人工审稿**（核对标题、尾图、排版）→ 点「发布」。

### 仅出 HTML（无凭证 / 手动发）
把 `publish_mode` 设为 `html`：脚本只产出 `drafts/*.html`，将正文分别粘贴到公众号编辑器即可（先 A 后 B）。

---

## 六、自动化链路

| 自动化 | 时间 | 职责 |
|--------|------|------|
| `automation-1784166639022`（Task1） | 每天 10:00 | 抓取近 7 日招聘文章，生成待审清单 `selected.json` |
| `automation-1784247680020`（Task2） | 每天 14:00 | 读 `selected_links.txt` →（有截图则视觉提取写 `extracted.json`）→ 跑本脚本 → 产出双稿并推草稿箱 |

> 人工选稿须在 Task2 运行前完成；若错过窗口，选好链接后可**手动触发 Task2 自动化**。因 Task1 每日重编号，脚本已按 `title` 回退匹配，仍能命中原文。

---

## 七、常见问题（FAQ）

**Q1：发布报 `40066 invalid url`？**
→ 99% 是端点或封面问题：确认用的是 `draft/add`（非 `freepublish/add`）且 `thumb_media_id` 是永久素材（`material/add_material` 返回）。其次检查是否有 `http://` 的 mmbiz 图未转 `https`。

**Q2：两篇草稿标题一样？**
→ 确认 `main()` 中 B 标题取自 `config.task2.articleB_title`（已修），不要拼 A 标题。

**Q3：草稿箱里尾图没了？**
→ 检查尾图是否插在最后一个 `</section>` 之前（代码已 `_place_tail_blocks` 处理）。校验是否被丢：看文末是否有 `margin:24px auto 0` 样式，而非看 URL/注释。

**Q4：取 `access_token` 报 `40164`？**
→ 运行环境出网 IP 不在公众号 IP 白名单。把报错里的 IP 加入公众号后台→开发→基本配置→IP 白名单。

**Q5：发文稿 B 没生成？**
→ 检查 `b_photos/extracted.json` 是否存在且为非空数组；没有则 B 跳过，仅出 A。

**Q6：想用真实 96 微信模板？**
→ 用 `crawl_96.py`（需 96 登录 cookie）抓取真实模板到 `templates/96/real/`，脚本会自动并入轮换（或设为 `articleB_style_fixed`）。
