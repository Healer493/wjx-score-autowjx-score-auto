# -*- coding: utf-8 -*-
"""
证书生成：读取 data_raw.json，为 ≥80 分的答卷生成矢量证书（PNG 300dpi + 矢量 PDF）
用法:
    python cert.py            # 增量生成（已存在的跳过）
    python cert.py --force    # 全部重生成
模板:
    cert_html.py 在原始设计稿坐标系里矢量重绘：
      red  = 环球商务英语（A2/B1/B2）
      blue = 经典英语（Level 1-9）
    主题在 cert_templates.json 的 series/levels 里按课程体系配置。
"""
import json, os, re, sys, time, hashlib
from datetime import datetime
import cert_html

# Pillow 只有「位图兜底」才用得到（正常的矢量渲染走 Chrome / node，不需要它）。
# 云端沙箱常常没装 Pillow，所以这里不硬依赖，缺了就跳过兜底、只报错。
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except Exception:                                   # pragma: no cover
    Image = ImageDraw = ImageFont = None
    PIL_OK = False

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "data_raw.json")
CERT_DIR = os.path.join(BASE, "证书")
INDEX = os.path.join(CERT_DIR, "index.json")
TPL_CONF = os.path.join(BASE, "cert_templates.json")
RENDER_JS = os.path.join(BASE, "render_cert.js")

EXCELLENT = 80
W, H = 1754, 1240          # A4 横向 @150dpi
MARGIN = 40

FONT_DIR = r"C:\Windows\Fonts"
F_ZH = os.path.join(FONT_DIR, "msyh.ttc")        # 微软雅黑
F_ZHB = os.path.join(FONT_DIR, "msyhbd.ttc")     # 微软雅黑 Bold
F_EN = os.path.join(FONT_DIR, "georgia.ttf")
F_ENI = os.path.join(FONT_DIR, "georgiai.ttf")
if not os.path.exists(F_EN):
    F_EN = F_ZHB
if not os.path.exists(F_ENI):
    F_ENI = F_ZH

# 三套级别配色：主色 / 浅色 / 强调
PALETTE = {
    "A2": {"main": (46, 125, 143), "soft": (223, 238, 241), "accent": (184, 137, 43)},
    "B1": {"main": (27, 79, 156), "soft": (223, 232, 245), "accent": (184, 137, 43)},
    "B2": {"main": (20, 49, 95), "soft": (219, 226, 238), "accent": (176, 122, 32)},
}
INK = (32, 38, 48)
INK2 = (92, 102, 118)
INK3 = (140, 150, 164)
PAPER = (253, 252, 249)
GOLD = (184, 137, 43)
GOLD_L = (214, 186, 128)


def F(path, size):
    return ImageFont.truetype(path, size)


def draw_spaced(draw, xy, text, font, fill, spacing=0, anchor_center_x=None):
    """带字距的文本绘制；给 anchor_center_x 则整体水平居中"""
    widths = []
    for ch in text:
        bb = font.getbbox(ch)
        widths.append(bb[2] - bb[0] if bb else 0)
    total = sum(widths) + spacing * max(0, len(text) - 1)
    x = (anchor_center_x - total / 2) if anchor_center_x is not None else xy[0]
    y = xy[1]
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing
    return total


def center(draw, y, text, font, fill, spacing=0):
    return draw_spaced(draw, (0, y), text, font, fill, spacing, anchor_center_x=W / 2)


def text_w(draw, text, font, spacing=0):
    w = 0
    for ch in text:
        bb = font.getbbox(ch)
        w += (bb[2] - bb[0]) + spacing
    return max(0, w - spacing)


def corner_ornament(d, x, y, dx, dy, color, size=46, width=2):
    """L 形角花"""
    d.line([(x, y), (x + dx * size, y)], fill=color, width=width)
    d.line([(x, y), (x, y + dy * size)], fill=color, width=width)
    # 小圆点
    r = 3
    d.ellipse([x - r, y - r, x + r, y + r], fill=color)


def clean_name(raw):
    """把"姓名与企业"里的噪声去掉：取第一段、去掉括号内容外的多余空白"""
    s = (raw or "").strip()
    s = re.sub(r"^[（(]?未填写[）)]?$", "", s)
    s = re.sub(r"\s+", " ", s)
    return s[:24] or "学员"


def cert_no(level, submit_time, jid):
    """证书编号：51T-A2-202611-3F7A"""
    ym = (submit_time or "")[:7].replace("-", "") or time.strftime("%Y%m")
    tail = hashlib.md5(str(jid).encode()).hexdigest()[:4].upper()
    return f"51T-{level}-{ym}-{tail}"


def build_builtin(level, name, score, submit_time, no):
    """内置绘制（无底图模板时）"""
    P = PALETTE.get(level, PALETTE["B1"])
    main, soft, accent = P["main"], P["soft"], P["accent"]

    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # 极淡底纹：右上角柔光块
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W - 620, -420, W + 340, 460], fill=26)
    gd.ellipse([-360, H - 460, 520, H + 380], fill=18)
    img = Image.composite(Image.new("RGB", (W, H), soft), img, glow)
    d = ImageDraw.Draw(img)

    # 边框
    d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=GOLD, width=3)
    d.rectangle([MARGIN + 14, MARGIN + 14, W - MARGIN - 14, H - MARGIN - 14],
                outline=GOLD_L, width=1)
    for (cx, cy, dx, dy) in [(MARGIN + 26, MARGIN + 26, 1, 1),
                             (W - MARGIN - 26, MARGIN + 26, -1, 1),
                             (MARGIN + 26, H - MARGIN - 26, 1, -1),
                             (W - MARGIN - 26, H - MARGIN - 26, -1, -1)]:
        corner_ornament(d, cx, cy, dx, dy, main, size=54, width=3)

    # 顶部品牌
    center(d, 96, "51TALK  ·  企业英语培训", F(F_ZHB, 21), main, spacing=4)
    d.line([(W/2 - 250, 146), (W/2 + 250, 146)], fill=GOLD_L, width=1)

    # 主标题
    center(d, 196, "CERTIFICATE OF ACHIEVEMENT", F(F_EN, 33), INK2, spacing=5)
    center(d, 250, "优 秀 证 书", F(F_ZHB, 82), main, spacing=10)

    # 级别徽章
    lv_text = f"{level}  级别"
    lw = text_w(d, lv_text, F(F_ZHB, 20), 2) + 44
    bx, by = W/2 - lw/2, 372
    d.rounded_rectangle([bx, by, bx + lw, by + 40], radius=20, fill=main)
    center(d, by + 8, lv_text, F(F_ZHB, 20), (255, 255, 255), spacing=2)

    # 姓名
    center(d, 466, "兹 证 明", F(F_ZH, 24), INK2, spacing=6)
    nfont = F(F_ZHB, 92)
    name_disp = clean_name(name)
    # 名字太长自动缩字号
    while text_w(d, name_disp, nfont, 6) > 900 and nfont.size > 44:
        nfont = F(F_ZHB, nfont.size - 6)
    center(d, 512, name_disp, nfont, INK, spacing=6)

    # 姓名下装饰线
    lw2 = min(560, max(240, text_w(d, name_disp, nfont, 6) + 80))
    d.line([(W/2 - lw2/2, 646), (W/2 + lw2/2, 646)], fill=GOLD, width=2)
    d.ellipse([W/2 - 4, 642, W/2 + 4, 650], fill=GOLD)

    # 正文
    ymd = submit_time[:10].replace("-", " 年 ", 1).replace("-", " 月 ", 1) + " 日"
    ymd = re.sub(r"\s+", " ", ymd).strip()
    if re.match(r"^\d{4} 年 \d{2} 月 \d{2} 日$", ymd):
        pass
    else:
        ymd = (submit_time or "")[:10]
    center(d, 690, f"于 {ymd} 完成「环球商务英语级别测试 {level}」", F(F_ZH, 27), INK2)
    center(d, 744, f"总分 {int(score) if float(score).is_integer() else score} / 100，"
                   f"成绩优异，达到优秀标准", F(F_ZH, 27), INK2)
    center(d, 798, "特此发证", F(F_ZH, 27), INK2, spacing=2)

    # 分数徽章
    sc = int(score) if float(score).is_integer() else round(score, 1)
    badge_w, badge_h = 210, 92
    bxx, byy = W/2 - badge_w/2, 862
    d.rounded_rectangle([bxx, byy, bxx + badge_w, byy + badge_h], radius=12,
                        fill=soft, outline=accent, width=2)
    d.text((W/2, byy + 12), "EXCELLENT", font=F(F_EN, 15), fill=accent, anchor="ma")
    d.text((W/2 - 10, byy + 32), str(sc), font=F(F_EN, 40), fill=main, anchor="ma")
    d.text((W/2 + 46, byy + 50), "分", font=F(F_ZH, 18), fill=INK2, anchor="ma")

    # 底部：编号 / 印章 / 日期
    foot_y = 1092
    d.text((MARGIN + 92, foot_y), f"证书编号  {no}", font=F(F_ZH, 19), fill=INK3)
    d.text((W - MARGIN - 92, foot_y), f"签发日期  {time.strftime('%Y 年 %m 月 %d 日')}",
           font=F(F_ZH, 19), fill=INK3, anchor="ra")

    # 简易印章
    cx, cy, r = W/2, 1078, 54
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(198, 60, 52), width=3)
    d.ellipse([cx - r + 7, cy - r + 7, cx + r - 7, cy + r - 7],
              outline=(198, 60, 52), width=1)
    d.text((cx, cy - 25), "51TALK", font=F(F_EN, 15), fill=(198, 60, 52), anchor="ma")
    d.text((cx, cy - 2), "企业英语", font=F(F_ZH, 14), fill=(198, 60, 52), anchor="ma")
    d.text((cx, cy + 18), "培训认证", font=F(F_ZH, 14), fill=(198, 60, 52), anchor="ma")

    return img


MONTHS_EN = ["January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]


def fmt_date_en(d):
    """2026-11-11 -> November 11, 2026"""
    try:
        y, m, dd = (d or "")[:10].split("-")
        return f"{MONTHS_EN[int(m) - 1]} {int(dd)}, {y}"
    except Exception:
        return d or ""


def build_from_template(cfg, level, name, score, submit_time, no):
    """图片叠加模式：cfg = {"image": 路径, "level_text": {...}, "fields": {name:{x,y,size,...}}}"""
    img = Image.open(cfg["image"]).convert("RGB")
    d = ImageDraw.Draw(img)
    f = cfg.get("fields", {})
    nm = clean_name(name)
    raw_date = (submit_time or "")[:10]
    values = {
        "name": nm,
        "level": (cfg.get("level_text") or {}).get(level, level),
        "level_raw": level,
        "score": str(int(score) if float(score).is_integer() else round(score, 1)),
        "date": fmt_date_en(raw_date) if cfg.get("date_style", "en") == "en" else raw_date,
        "issued": fmt_date_en(time.strftime("%Y-%m-%d")),
        "no": no,
    }
    for key, spec in f.items():
        txt = values.get(key, "")
        if not txt:
            continue
        size = spec.get("size", 40)
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", txt))
        fontpath = spec.get("font_zh" if has_cjk else "font_en") or spec.get("font") or F_ZHB
        if not os.path.exists(fontpath):
            fontpath = F_ZHB
        font = F(fontpath, size)
        color = tuple(spec.get("color", [32, 38, 48]))
        align = spec.get("align", "center")
        x, y = spec.get("x", img.width / 2), spec.get("y", img.height / 2)
        maxw = spec.get("maxw", 900)
        spacing = spec.get("spacing", 0)
        while text_w(d, txt, font, spacing) > maxw and font.size > 14:
            font = F(fontpath, font.size - 2)
        if align == "center":
            draw_spaced(d, (0, y), txt, font, color, spacing, anchor_center_x=x)
        elif align == "right":
            tw = text_w(d, txt, font, spacing)
            draw_spaced(d, (x - tw, y), txt, font, color, spacing)
        else:
            draw_spaced(d, (x, y), txt, font, color, spacing)
    return img


def resolve_level(conf, level):
    """返回 (theme, 级别配置)。兼容旧结构（以级别为键、带 image 字段）。"""
    lv = (conf.get("levels") or {}).get(level) or {}
    theme = lv.get("theme")
    if not theme and lv.get("series"):
        theme = ((conf.get("series") or {}).get(lv["series"]) or {}).get("theme")
    if not theme:
        old = conf.get(level) or {}
        if old.get("image"):
            theme = "red"
    return (theme or "red"), lv


def safe_slug(s):
    return re.sub(r'[\\/:*?"<>|\s]+', '_', str(s or '')).strip('_') or 'cert'


def find_node():
    """优先 PATH，其次常见安装位置（Linux 服务器 / 双击 bat 时 PATH 往往不含 node）"""
    import shutil, glob
    for cand in ("node", "nodejs"):
        p = shutil.which(cand)
        if p:
            return p
    pats = [
        # Linux / macOS
        "/usr/bin/node", "/usr/local/bin/node", "/usr/bin/nodejs",
        "/opt/node/bin/node", os.path.expanduser("~/.nvm/versions/node/*/bin/node"),
        # Windows
        os.path.expanduser(r"~\.workbuddy\binaries\node\versions\*\node.exe"),
        r"C:\Program Files\nodejs\node.exe",
        os.path.expanduser(r"~\.workbuddy\binaries\node\*\node.exe"),
    ]
    for pat in pats:
        if os.path.exists(pat):
            return pat
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def render_vector(todo, conf):
    """渲染矢量证书：优先 Chrome 命令行（不依赖 node / npm），其次 node + puppeteer。"""
    import subprocess
    payload = []
    for it in todo:
        theme, lv = resolve_level(conf, it["level"])
        payload.append({
            "theme": theme,
            "slug": it["slug"],
            "name": it["name"],
            "level_en": lv.get("level_en", ""),
            "level_no": lv.get("level_no", ""),
            "level_code": it["level"],
            "submit_time": it["submit_time"],
        })
    items = [{
        "theme": p["theme"], "slug": p["slug"], "name": p["name"],
        "level_en": p["level_en"], "level_no": p["level_no"],
        "level_code": p["level_code"],
        "date": p["submit_time"],
    } for p in payload]

    # ── 1) Chrome 命令行渲染：不依赖 node / npm，云端定时任务首选
    try:
        import render_cert_chrome
        if render_cert_chrome.find_chrome():
            pages = [{"slug": it["slug"], "html": cert_html.render_pages([it])} for it in items]
            render_cert_chrome.render(pages, CERT_DIR, "both", log=lambda s: None)
            done = sum(1 for it in todo if os.path.exists(os.path.join(CERT_DIR, it["slug"] + ".png")))
            if done == len(todo):
                print(f"  矢量渲染完成 {done}/{len(todo)}（Chrome 命令行）")
                return True
            print(f"  ! Chrome 命令行只出了 {done}/{len(todo)}，改用 node 渲染")
        else:
            print("  ! 未找到 Chrome/Chromium，改用 node 渲染")
    except Exception as e:
        print(f"  ! Chrome 命令行渲染异常（{e}），改用 node 渲染")

    # ── 2) node + puppeteer 兜底
    node_exe = find_node()
    if not node_exe:
        print("  ! 未找到 node，回退到位图模式")
        return False

    html = cert_html.render_pages(items)
    tmp = os.path.join(BASE, "_cert_build.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    env = os.environ.copy()
    nm = os.path.join(BASE, "node_modules")
    if os.path.isdir(nm):
        env["NODE_PATH"] = nm
    try:
        r = subprocess.run([node_exe, RENDER_JS, tmp, CERT_DIR, "both"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=600)
    except FileNotFoundError:
        print("  ! 未找到 node，回退到位图模式")
        return False
    except subprocess.TimeoutExpired:
        print("  ! node 渲染超时，回退到位图模式")
        return False
    if r.returncode != 0:
        print("  ! node 渲染失败：", (r.stderr or "")[:400])
        return False
    ok = sum(1 for it in todo if os.path.exists(os.path.join(CERT_DIR, it["slug"] + ".png")))
    print(f"  矢量渲染完成 {ok}/{len(todo)}")
    return ok == len(todo)


def main():
    force = "--force" in sys.argv
    if not os.path.exists(RAW):
        raise SystemExit("找不到 data_raw.json，先运行 update.py")
    data = json.load(open(RAW, encoding="utf-8"))
    conf = {}
    if os.path.exists(TPL_CONF):
        try:
            conf = json.load(open(TPL_CONF, encoding="utf-8"))
        except Exception as e:
            print("模板配置解析失败，改用内置绘制:", e)

    os.makedirs(CERT_DIR, exist_ok=True)
    old = {}
    if os.path.exists(INDEX):
        try:
            old = {x["key"]: x for x in json.load(open(INDEX, encoding="utf-8"))}
        except Exception:
            old = {}

    items = []
    for level in sorted(data["levels"].keys()):
        L = data["levels"].get(level)
        if not L:
            continue
        theme, lv = resolve_level(conf, level)
        for r in L["records"]:
            try:
                sc = float(r["score"])
            except Exception:
                continue
            if sc < EXCELLENT:
                continue
            key = f"{level}:{r['jid']}"
            no = cert_no(level, r.get("submit_time", ""), r["jid"])
            slug = f"{level}_{safe_slug(clean_name(r['name']))}_{int(sc)}_{no[-4:]}"
            items.append({
                "key": key, "level": level, "jid": r["jid"],
                "name": clean_name(r["name"]), "score": sc,
                "submit_time": r.get("submit_time", ""),
                "no": no, "slug": slug,
                "file": slug + ".png", "pdf": slug + ".pdf",
                "theme": theme, "series": lv.get("series", ""),
                "template": "vector-" + theme,
            })

    todo = [it for it in items
            if force or not os.path.exists(os.path.join(CERT_DIR, it["slug"] + ".png"))]
    skipped = len(items) - len(todo)
    if todo:
        print(f"  生成 {len(todo)} 张矢量证书…")
        if not render_vector(todo, conf):
            if not PIL_OK:
                print("  ! 矢量渲染失败，且环境没有 Pillow，无法走位图兜底")
                print("    （解决办法：安装 Chrome/Chromium，或 pip install pillow）")
                return 1
            print("  → 改走位图模式（清晰度较低）")
            for it in todo:
                try:
                    tpl = (conf.get(it["level"]) or {})
                    tpl_img = tpl.get("image")
                    if tpl_img and not os.path.isabs(tpl_img):
                        tpl_img = os.path.join(BASE, tpl_img)
                    if tpl_img and os.path.exists(tpl_img):
                        tpl = dict(tpl); tpl["image"] = tpl_img
                        img = build_from_template(tpl, it["level"], it["name"], it["score"],
                                                  it["submit_time"], it["no"])
                    else:
                        img = build_builtin(it["level"], it["name"], it["score"],
                                            it["submit_time"], it["no"])
                    img.save(os.path.join(CERT_DIR, it["file"]), "PNG", optimize=True)
                    img.save(os.path.join(CERT_DIR, it["pdf"]), "PDF", resolution=300.0)
                    print("  + " + it["file"])
                except Exception as e:
                    print("  ! 生成失败", it["file"], e)

    # 兼容：旧索引里若缺 slug/pdf，回填
    for it in items:
        it.setdefault("slug", it["file"][:-4])

    items.sort(key=lambda x: (x["level"], -float(x["score"])))
    json.dump(items, open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if os.path.exists(os.path.join(BASE, "_cert_build.html")):
        os.remove(os.path.join(BASE, "_cert_build.html"))
    print(f"\n证书：新生成 {len(todo)} 张，复用 {skipped} 张，共 {len(items)} 张 -> {CERT_DIR}")
    return items


if __name__ == "__main__":
    main()
