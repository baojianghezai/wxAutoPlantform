# -*- coding: utf-8 -*-
"""微信公众号草稿箱发布模块（从 task2_publish.py 原样提炼，仅标准库）。

对外接口：
    push_to_draft(title, content_html, author="", digest="") -> str
        推送到公众号草稿箱（cgi-bin/draft/add），成功返回 media_id；
        失败抛 RuntimeError，异常信息中带微信 errcode/响应内容。

配置来源（路径相对【项目根】解析，即本文件所在 publish/ 的上一级）：
    · 凭证：环境变量 WECHAT_APPID / WECHAT_SECRET 优先，回退项目根 config.json 的 wechat.appid/secret；
    · 尾图目录：config.json 的 task2.tail_images_dir（默认 tail_images）；
    · 封面回退图：assets/fixed_tail.png。

发布流程（与原 task2_publish.publish_to_draft 一致）：
    access_token → 尾图预上传换 mmbiz URL 并挪到最后 </section> 之前
    → 清洗正文（data-src→src、内联 data: 图上传、mmbiz 强制 https）
    → 上传永久封面取 thumb_media_id → cgi-bin/draft/add。

依赖：仅 Python 标准库（urllib / base64 / json / re）。
"""
import json, os, re, base64, urllib.request, urllib.error, uuid

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根（publish/ 的上一级）

DEFAULTS = {
    "task2": {
        "tail_images_dir": "tail_images",
    },
    "wechat": {"accounts": [], "appid": "", "secret": ""},
}

config = dict(DEFAULTS)
cfg_path = os.path.join(BASE, "config.json")
if os.path.exists(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    config.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    config["task2"].update(cfg.get("task2", {}))
    config["wechat"].update(cfg.get("wechat", {}))

T2 = config["task2"]


def _get_accounts():
    """返回公众号凭证列表 [{id, name, appid, secret}]。

    优先读 config.json 的 wechat.accounts；若为空则用旧式单账号 wechat.appid/secret
    合成 id="default" 的账号，保证向后兼容。
    """
    accounts = config["wechat"].get("accounts") or []
    if accounts:
        return accounts
    appid = os.environ.get("WECHAT_APPID") or config["wechat"].get("appid")
    secret = os.environ.get("WECHAT_SECRET") or config["wechat"].get("secret")
    if appid:
        return [{"id": "default", "name": "默认公众号", "appid": appid, "secret": secret}]
    return []


def _get_credentials(account_id=None):
    """返回指定账号 (account_id) 的 (appid, secret)。

    account_id 为空时回退旧式单账号（环境变量优先，再 config.json wechat.appid/secret）。
    """
    if account_id:
        for acc in _get_accounts():
            if acc.get("id") == account_id:
                return acc.get("appid", ""), acc.get("secret", "")
        raise RuntimeError(f"未找到公众号账号: {account_id}")
    appid = os.environ.get("WECHAT_APPID") or config["wechat"].get("appid")
    secret = os.environ.get("WECHAT_SECRET") or config["wechat"].get("secret")
    return appid, secret


def _get_access_token(appid, secret):
    """获取 access_token；失败抛异常并带微信响应内容。"""
    tok_url = (f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential"
               f"&appid={appid}&secret={secret}")
    tok = json.load(urllib.request.urlopen(tok_url, timeout=20))
    if "access_token" not in tok:
        raise RuntimeError(f"获取 access_token 失败: {tok}")
    return tok["access_token"]


def _upload_inline_image(at, mime, raw_bytes, ext):
    """把一张图片字节上传到微信素材库，返回 mmbiz URL 或 None（带重试）。"""
    last_err = ""
    for attempt in range(3):
        try:
            boundary = "----WB" + uuid.uuid4().hex
            body = (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="media"; filename="img.{ext}"\r\n'
                    f"Content-Type: {mime}\r\n\r\n").encode() + raw_bytes + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={at}",
                data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            resp = json.load(urllib.request.urlopen(req, timeout=30))
            if "url" in resp:
                return resp["url"]
            last_err = str(resp)
        except Exception as e:
            last_err = repr(e)
        print(f"  · 上传图片第{attempt+1}次失败: {last_err}")
    return None


def _sanitize_for_publish(content, at):
    """发布前清洗：data-src→src 还原真实图；内联 data: 图上传为 mmbiz 地址。"""
    # 1) 微信懒加载：data-src 才是真实图，移到 src（并去掉原占位 src）
    def move_datassrc(m):
        pre, real, post = m.group(1), m.group(2), m.group(3)
        pre = re.sub(r'\ssrc="[^"]*"', '', pre)
        post = re.sub(r'\ssrc="[^"]*"', '', post)
        return f'<img{pre} src="{real}"{post}'
    content = re.sub(r'<img\b([^>]*?)\bdata-src="([^"]+)"([^>]*)>', move_datassrc, content)
    # 2) 把内联 data:image 图都上传并替换（尾图 / 任何 base64 内联图）
    def up(m):
        mime = m.group(1)
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
               "image/gif": "gif", "image/webp": "webp"}.get(mime, "png")
        url = _upload_inline_image(at, mime, raw, ext)
        if url:
            return url
        return m.group(0)
    # 注意：re.sub 必须在 up() 函数体【之外】调用，否则上面的 return 会让它成为死代码
    content = re.sub(r'data:([^;]+);base64,([A-Za-z0-9+/=]+)', up, content)
    # 3) mmbiz 图强制 https（freepublish/add 拒绝 http:// 图，报 40066 invalid url）
    content = content.replace("http://mmbiz.qpic.cn", "https://mmbiz.qpic.cn")
    content = content.replace("http://mp.weixin.qq.com", "https://mp.weixin.qq.com")
    return content


def _upload_permanent_image(at, path):
    """上传图片到【永久素材】，返回 media_id（用作封面 thumb_media_id）。
    注意：正文配图用 media/uploadimg（返回 mmbiz URL）；封面必须用永久 media_id。"""
    if not (path and os.path.exists(path)):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
    raw = open(path, "rb").read()
    boundary = "----WB" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; "
            f"filename=\"c{ext}\"\r\nContent-Type: {mime}\r\n\r\n").encode() \
           + raw + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={at}&type=image",
        data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=30))
        return resp.get("media_id")
    except Exception as e:
        print(f"  · 封面上传失败: {e}")
        return None


def _get_thumb_media_id(at):
    """取封面永久 media_id：优先 tail_images 首图，回退 assets/fixed_tail.png。"""
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    if os.path.isdir(tail_dir):
        for fn in sorted(os.listdir(tail_dir)):
            fp = os.path.join(tail_dir, fn)
            if os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
                mid = _upload_permanent_image(at, fp)
                if mid:
                    return mid
    fallback = os.path.join(BASE, "assets", "fixed_tail.png")
    if os.path.exists(fallback):
        return _upload_permanent_image(at, fallback)
    return None


def _attach_tail_images(content, at):
    """发布前把尾图（tail_images/ 下图片，构建时为 data: 内联）预上传为 mmbiz 地址并直接替换，
    确保两篇草稿文末都带真实图床图（不依赖 _sanitize 对大段 base64 的正则碰运气）。"""
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    if not os.path.isdir(tail_dir):
        return content
    for fn in sorted(os.listdir(tail_dir)):
        fp = os.path.join(tail_dir, fn)
        if not (os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp")):
            continue
        ext = os.path.splitext(fp)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        raw = open(fp, "rb").read()
        url = _upload_inline_image(at, mime, raw, ext)
        if not url:
            print(f"  · 尾图 {fn} 上传失败，跳过（data: 将由 _sanitize 兜底）")
            continue
        url = url.replace("http://", "https://")
        marker = f"<!-- TAILIMG:{fn} -->"
        pat = r'<img\b([^>]*?)src="data:[^"]*"([^>]*?)>\s*' + re.escape(marker)
        content = re.sub(pat, lambda m: f'<img{m.group(1)}src="{url}"{m.group(2)}>' + marker, content)
    # 关键：微信 draft/add 会把正文末尾那串 </section> 之后的「兄弟节点」当文末垃圾丢弃。
    # 所以把所有尾图块移动到最后一个 </section> 之前（仍属正文内容树），确保入箱后可见。
    return _place_tail_blocks(content)


def _place_tail_blocks(content):
    """把 <!-- TAILIMG --> 尾图块（独立 <section> 包裹）挪到【最后一个 </section> 之内、作为该节最末子节点】。

    微信规则：会丢弃「正文最后一个 </section> 闭合标签之后的兄弟节点」。
    因此尾图必须留在最后一个 </section> 之内（不能甩在它之外），同时又是该节
    的【最后】子节点 → 既不被丢，又显示在该节末尾 = 整篇文末。

    对真实微信图文（A，正文本身多层 </section> 嵌套）这一点尤其关键：
    追加到整篇最末尾会落回"最后 </section> 之外"被丢弃；只有插进最后一个
    </section> 内部并置于其末尾才稳妥。
    """
    # 优先匹配 <section>...</section> 包裹的尾图块（新格式）
    blocks = re.findall(r'<section\b[^>]*>\s*<img[^>]*>\s*<!-- TAILIMG:[^>]*-->\s*</section>', content)
    if not blocks:
        bare = re.findall(r'<img[^>]*>\s*<!-- TAILIMG:[^>]*-->', content)
        blocks = [f'<section style="box-sizing:border-box;">{b}</section>' for b in bare]
    if not blocks:
        return content
    for b in blocks:
        content = content.replace(b, "")
    idx = content.rfind("</section>")
    if idx == -1:
        idx = content.rfind("</body>")
    if idx == -1:
        idx = len(content)
    return content[:idx] + "".join(blocks) + content[idx:]


def push_to_draft(title: str, content_html: str, author: str = "", digest: str = "",
                  account_id: str | None = None) -> str:
    """按官方规则清洗内容并推送到草稿箱（cgi-bin/draft/add）。

    必填：title(≤32字) / content_html / thumb_media_id(永久封面)。
    account_id：目标公众号 id（config.json 的 wechat.accounts），为空时回退旧式单账号。
    成功返回 media_id；失败抛 RuntimeError，异常信息带微信 errcode/响应内容。
    """
    appid, secret = _get_credentials(account_id)
    if not (appid and secret):
        raise RuntimeError("未配置微信 appid/secret（请设置环境变量 WECHAT_APPID/WECHAT_SECRET "
                           "或在项目根 config.json 的 wechat.accounts 中配置对应账号）")
    try:
        # 1) access_token
        at = _get_access_token(appid, secret)
        # 2) 先把尾图预上传并替换为真实 mmbiz 地址（文末都带）
        content = _attach_tail_images(content_html, at)
        # 3) 清洗内容（内联 data: 图上传为 mmbiz；data-src→src；http→https）
        content = _sanitize_for_publish(content, at)
        # 4) 封面永久 media_id（draft/add 必填）
        thumb = _get_thumb_media_id(at)
        if not thumb:
            raise RuntimeError("无法获取封面 media_id（封面图上传失败）")
        # 5) 标题原样使用（不截断）、摘要≤128字
        title = title or "未命名文章"
        digest = (digest or "")[:128]
        payload = {"articles": [{
            "title": title,
            "author": author or "",
            "digest": digest,
            "content": content,
            "content_source_url": "",
            "thumb_media_id": thumb,
        }]}
        add_url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={at}"
        req = urllib.request.Request(add_url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        resp = json.load(urllib.request.urlopen(req, timeout=30))
        if resp.get("errcode") == 0 or "media_id" in resp:
            return resp.get("media_id")
        raise RuntimeError(f"draft/add 失败 errcode={resp.get('errcode')} errmsg={resp.get('errmsg')}: {resp}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"发布异常: {e}") from e


if __name__ == "__main__":
    # 冒烟测试：用一小段测试 HTML 做一次真实推送，打印 media_id。
    test_html = (
        '<!doctype html><html lang=zh><head><meta charset=utf-8></head><body>'
        '<section style="box-sizing:border-box;">'
        '<p>这是一条 publish 模块的冒烟测试草稿，请忽略。</p>'
        '</section></body></html>'
    )
    mid = push_to_draft("publish 模块冒烟测试", test_html,
                        author="自动化脚本", digest="冒烟测试，请忽略")
    print(f"✔ 推送成功，media_id={mid}")
