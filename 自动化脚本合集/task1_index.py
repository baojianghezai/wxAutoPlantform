# -*- coding: utf-8 -*-
"""Task1 Index — 轻量索引生成器。
从本地 RSS 聚合器拉取全量数据，按 14 天窗口 + 目标账号 + 招聘关键词过滤，
生成【轻量 index.json】（供 32k 模型直接读取）和【简化 index.html】（人工浏览）。

特点：
- 不存储完整 HTML，仅保留摘要/元数据，文件体积控制在 100KB 以内
- index.json 可直接喂给模型做选题分析，无需再处理大体积 RSS
- 若需看原文，可通过 link 字段跳转，或配合 candidates/ 目录使用

依赖：仅 Python 标准库。
用法：python task1_index.py
"""
import json, os, re, html as html_mod
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "rss_url": "http://192.168.10.240:5000/api/rss/all",
    "days": 14,
    "accounts": {
        "gov": ["青岛市国企招聘", "青岛人才", "青岛12333", "青岛人社"],
        "media": ["半岛都市报即墨", "山东华图"],
    },
    "cross_account_aliases": [["水发集团"], ["李沧区"]],
    "review_dir": "review",
    "rss_cache": "rss_cache.xml",
    "max_images": 12,
    "index_json": "index.json",
    "index_html": "index.html",
}

config = dict(DEFAULTS)
cfg_path = os.path.join(BASE, "config.json")
if os.path.exists(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        config.update(json.load(f))

GOV = set(config["accounts"].get("gov", []))
MEDIA = set(config["accounts"].get("media", []))
TARGET = GOV | MEDIA
ALIASES = config.get("cross_account_aliases", [])

# 过滤规则
POS = re.compile(r'招(聘|录|募|考|生|人|贤)|引进|招募|公招|人才引进|诚聘|岗位|上新|纳新|招考')
EXC = re.compile(r'高频热点|科普|常识|时政|模考|技能等级证书|技能培训|公益课堂|台风|天气|强对流|降雨|'
                 r'油价|通报|行政处罚|风采|年休假|失业金|退休|人事档案|实习期|试用期|拖欠工资|高温|'
                 r'��伏|三伏|风险提示|海底隧道|风景区|体检人员名单|进入体检|成绩及|如何办理|怎么认|'
                 r'怎么办|如何申请|领取条件|纠纷|投诉|提醒|社保|一课|课堂|说清|一文|速存|免租|'
                 r'劳动合同|打工人|必读|维权|夜市|开市|出摊|以案|典型案例|法定义务')

DEADLINE_KEEP = re.compile(r'招满即止|招满为止|长期(招聘|有效|招募)|常年(招聘|招募)|滚动(招聘|招募)|不限时间|长期招')
DATE_RE = re.compile(r'(?:(?P<y>20\d{2})\s*年)?\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日?(?:\s*(?P<h>\d{1,2}):(?P<min>\d{2}))?')
DATE_ISO_RE = re.compile(r'(?P<y>20\d{2})[-/](?P<m>\d{1,2})[-/](?P<d>\d{1,2})(?:\s*(?P<h>\d{1,2}):(?P<min>\d{2}))?')


def _date_to_dt(m, default_year):
    if not m:
        return None
    y = m.group('y')
    try:
        return datetime(int(y) if y else default_year, int(m.group('m')), int(m.group('d')),
                        int(m.group('h')) if m.group('h') else 0,
                        int(m.group('min')) if m.group('min') else 0, tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        return None


def extract_deadline(text, now_year):
    if DEADLINE_KEEP.search(text):
        return None
    cands = []
    for kw in ['截止时间', '截止日期', '报名截止至', '报名截止时间', '报名截至', '报名截止', '截止']:
        for m in re.finditer(re.escape(kw), text):
            seg = text[m.end(): m.end() + 22]
            dt = _date_to_dt(DATE_RE.search(seg) or DATE_ISO_RE.search(seg), now_year)
            if dt:
                cands.append(dt)
    for m in re.finditer(r'报名[^。，,；;]{0,30}?至', text):
        seg = text[m.end(): m.end() + 22]
        dt = _date_to_dt(DATE_RE.search(seg) or DATE_ISO_RE.search(seg), now_year)
        if dt:
            cands.append(dt)
    for m in re.finditer(r'(?:(?:20\d{2}\s*年)?\s*\d{1,2}\s*月\s*\d{1,2}\s*日?)\s*截止', text):
        dt = _date_to_dt(DATE_RE.search(m.group(0)), now_year)
        if dt:
            cands.append(dt)
    return max(cands) if cands else None


def fetch_rss():
    try:
        req = urllib.request.Request(config["rss_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        cache = os.path.join(BASE, config["rss_cache"])
        with open(cache, "wb") as f:
            f.write(data)
        return cache, None
    except Exception as e:
        return None, str(e)


def parse_dt(s):
    try:
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return None


def acct_of(t):
    return t.split(']')[0].lstrip('[') if t.startswith('[') else '(无前缀)'


def strip_prefix(t):
    return t.split(']', 1)[1].strip() if ']' in t else t


def clean(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = html_mod.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()


def extract_companies(text):
    COMPANY_RE = re.compile(
        r'([一-鿿]{2,12}?)'
        r'(集团有限公司|集团股份有限公司|集团|股份有限公司|股份公司|有限责任公司|有限公司|'
        r'银行|医院|大学|学院|学校|研究院|研究所|事务所|出版社|中心|局|委|管委会)')
    found = []
    for m in COMPANY_RE.finditer(text):
        name = m.group(1) + m.group(2)
        if len(name) >= 4 and name not in found:
            found.append(name)
    for k in config.get("known_companies", []):
        if k and k in text and k not in found:
            found.append(k)
    return found[:10]


def core(t):
    t = re.sub(r'\[[^\]]*\]', '', t)
    t = re.sub(r'[‼️⏰🔥💥🤗→]', '', t)
    t = re.sub(r'(20\d\d年|20\d\d年度)', '', t)
    t = re.sub(r'(今日报名|明日报名|7月\d+日报名|正在报名中|报名中|国企新招|岗位丰富|新招\d+人|国企\d+人|'
               r'二招|八险二金|待遇可观|月薪[\dK\+万以上]+|人数若干|部分不限专业|不限专业|专科有岗|速看|'
               r'招聘工作人员|招聘公告|公开招聘|招聘|招录|引进|招募|人才引进|诚聘|岗位|上新|纳新|招考|！|!|,|，)', ' ', t)
    t = re.sub(r'\s+', '', t)
    return t


def same_group(r1, r2):
    c1, c2 = core(r1['title']), core(r2['title'])
    if c1 and c1 == c2:
        return True
    for grp in ALIASES:
        if all(k in r1['title'] and k in r2['title'] for k in grp):
            return True
    return False


# ---------- 主流程 ----------
NOW = datetime.now(timezone(timedelta(hours=8)))
LO = NOW - timedelta(days=config["days"])
HI = NOW
NOW_STR = NOW.strftime("%Y-%m-%d %H:%M")
LO_STR = LO.strftime("%Y-%m-%d %H:%M")
HI_STR = HI.strftime("%Y-%m-%d %H:%M")

cache, rss_err = fetch_rss()
rss_ok = cache is not None

rows = []
expired_filtered = 0
expired_list = []
if rss_ok:
    tree = ET.parse(cache)
    items = tree.getroot().find('channel').findall('item')
    for it in items:
        raw = (it.findtext('title') or '').strip()
        pub = it.findtext('pubDate')
        dt = parse_dt(pub)
        link = it.findtext('link') or ''
        desc = it.findtext('description') or ''
        acct = acct_of(raw)
        if dt is None or not (LO <= dt <= HI):
            continue
        if acct not in TARGET:
            continue
        keep = bool(POS.search(raw)) and not EXC.search(raw)
        if not keep:
            continue
        text = clean(desc)
        deadline = extract_deadline(raw + ' ' + text[:2500], NOW.year)
        if deadline is not None and deadline < NOW:
            expired_filtered += 1
            expired_list.append((acct, strip_prefix(raw), deadline.strftime("%Y-%m-%d %H:%M")))
            continue
        imgs = [u for u in re.findall(r'src="([^"]+)"', desc) if 'mmbiz' in u or '/api/image' in u]
        atts = re.findall(r'href="([^"]+\.(?:docx?|xlsx?|pdf|csv))"', desc, re.I)
        atts += re.findall(r'href="(https?://[^"]*(?:docin|tencentdoc|wps|docs\.qq)[^"]*)"', desc, re.I)
        rows.append({
            'acct': acct, 'raw': raw, 'title': strip_prefix(raw),
            'link': link, 'raw_pub': pub, 'dt': dt,
            'summary': text[:300], 'imgs': imgs[:config["max_images"]], 'atts': atts[:5],
            'deadline': deadline,
        })

# ---------- 去重 ----------
merged = []
used = [False] * len(rows)
for i in range(len(rows)):
    if used[i]:
        continue
    grp = [rows[i]]
    used[i] = True
    for j in range(i + 1, len(rows)):
        if not used[j] and same_group(rows[i], rows[j]):
            grp.append(rows[j])
            used[j] = True
    grp.sort(key=lambda r: (0 if r['acct'] in GOV else 1, r['dt']))
    merged.append(grp)

# ---------- 生成轻量 index.json（供 AI 直接读取）----------
results = []
for idx, grp in enumerate(merged, 1):
    aid = f"A{idx:02d}"
    rep = grp[0]
    meta = {
        "id": aid,
        "accounts": sorted({r['acct'] for r in grp}),
        "title": rep['title'],
        "link": rep['link'] if len(grp) == 1 else [r['link'] for r in grp],
        "pubDate": rep['raw_pub'],
        "deadline": rep['deadline'].strftime("%Y-%m-%d %H:%M") if rep.get('deadline') else "",
        "summary": rep['summary'],
        "image_count": len(rep['imgs']),
        "first_image": rep['imgs'][0] if rep['imgs'] else "",
        "attachments": rep['atts'][:5],
        "companies": extract_companies(rep['raw'] + ' ' + rep['summary']),
        "is_media": rep['acct'] in MEDIA,
        "note": "媒体/机构账号：阅读量未核实，需人工复核≥1000" if rep['acct'] in MEDIA else "",
    }
    results.append(meta)

review_dir = os.path.join(BASE, config["review_dir"])
os.makedirs(review_dir, exist_ok=True)

index_json_path = os.path.join(review_dir, config["index_json"])
with open(index_json_path, "w", encoding="utf-8") as f:
    json.dump({
        "generated_at": NOW_STR,
        "window": [LO_STR, HI_STR],
        "candidate_count": len(results),
        "expired_filtered": expired_filtered,
        "items": results,
    }, f, ensure_ascii=False, indent=2)

# ---------- 生成简化 index.html（人工浏览用）----------
def gen_review(results, rss_ok, rss_err):
    p = []
    p.append(f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>待审清单（轻量）</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f5f6f8;color:#222}}
 header{{background:#1F4E78;color:#fff;padding:18px 24px}}
 header h1{{margin:0;font-size:20px}} header p{{margin:6px 0 0;opacity:.85;font-size:13px}}
 .wrap{{max-width:960px;margin:0 auto;padding:20px}}
 .card{{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin:14px 0;padding:16px;display:flex;gap:16px}}
 .thumb{{width:120px;min-width:120px;height:120px;object-fit:cover;border-radius:8px;background:#eee}}
 .body{{flex:1}} .idbadge{{display:inline-block;background:#1F4E78;color:#fff;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:700;margin-right:8px}}
 .acct{{color:#1F4E78;font-weight:600;font-size:13px}} .title{{font-size:16px;font-weight:700;margin:6px 0}}
 .meta{{color:#888;font-size:12px;margin:4px 0}} .summary{{font-size:13px;color:#444;margin:8px 0;line-height:1.5}}
 .note{{font-size:12px;color:#b8860b;background:#fff7e0;padding:4px 8px;border-radius:6px;display:inline-block}}
 .links a{{color:#1F4E78;font-size:12px;margin-right:10px;text-decoration:none}}
 .empty{{text-align:center;color:#888;padding:60px}} .tip{{background:#eef4fb;border-left:4px solid #1F4E78;padding:10px 14px;font-size:13px;margin:14px 0;border-radius:6px}}
 code{{background:#eef;padding:2px 6px;border-radius:4px}}
</style></head><body>
<header><h1>公众号招聘 · 待审清单（轻量索引）</h1>
<p>生成时间：{NOW_STR} ｜ 窗口：{LO_STR} ~ {HI_STR} ｜ 候选：{len(results)} 篇 ｜ 已过期过滤：{expired_filtered} 篇</p></header>
<div class=wrap>
<div class=tip>提示：本页为轻量索引，仅含元数据。若需查看完整原文，请打开 candidates/ 目录下的对应 HTML 文件，或点击原文链接。index.json 已生成，可直接供 AI 读取分析。</div>
""")
    if not rss_ok:
        p.append(f'<div class="empty">⚠️ RSS 源不可用（{rss_err}），本次未生成候选。请确认 http://192.168.10.240:5000 已启动。</div>')
    if not results:
        p.append(f'<div class="empty">近 {config["days"]} 天目标号无符合条件的官方招聘公告。</div>')
    for m in results:
        img = m['first_image']
        img_tag = f'<img class=thumb src="{img}" alt="">' if img else '<div class=thumb></div>'
        links = m['link']
        if isinstance(links, list):
            link_html = ' '.join(f'<a href="{l}" target=_blank>原文{i+1}</a>' for i, l in enumerate(links))
        else:
            link_html = f'<a href="{links}" target=_blank>原文链接</a>'
        att = '；'.join(m['attachments'][:3]) if m['attachments'] else '无'
        dl = f" ｜ 报名截止：{m['deadline']}" if m['deadline'] else ""
        p.append(f"""
<div class=card> {img_tag}
 <div class=body>
  <span class=idbadge>{m['id']}</span><span class=acct>{' / '.join(m['accounts'])}</span>
  <div class=title>{m['title']}</div>
  <div class=meta>发布：{m['pubDate']} ｜ 配图：{m['image_count']}张 ｜ 附件：{att}{dl}</div>
  <div class=summary>{m['summary']}</div>
  {('<div class=meta>线索企业：' + '、'.join(m.get('companies', []) or []) + '</div>') if m.get('companies') else ''}
  {('<div class=note>'+m['note']+'</div>') if m['note'] else ''}
  <div class=links>{link_html}</div>
 </div>
</div>""")
    p.append('</div></body></html>')
    with open(os.path.join(review_dir, config["index_html"]), "w", encoding="utf-8") as f:
        f.write('\n'.join(p))


gen_review(results, rss_ok, rss_err)

# ---------- 运行状态 ----------
status = {
    "run_at": NOW_STR, "rss_ok": rss_ok, "rss_error": rss_err or "",
    "window": [LO_STR, HI_STR], "candidate_count": len(results),
    "expired_filtered": expired_filtered, "days": config["days"],
}
with open(os.path.join(BASE, "task1_status.json"), "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)

print(f"RSS: {'OK' if rss_ok else 'FAIL ' + str(rss_err)}")
print(f"候选(去重后): {len(results)} 篇 ｜ 已过期过滤: {expired_filtered} 篇 ｜ ��口: {LO_STR} ~ {HI_STR}")
print(f"轻量索引: {index_json_path}")
print(f"待审清单: {os.path.join(review_dir, config['index_html'])}")
if expired_filtered:
    print("已过期(截止时间早于当前)被过滤:")
    for acct, title, dl in expired_list:
        print(f"  × [{acct}] {title[:36]} ｜ 截止 {dl}")
for m in results:
    print(f"  {m['id']} [{','.join(m['accounts'])}] {m['title'][:40]}" + (f" ｜ 截止 {m['deadline']}" if m['deadline'] else ""))
