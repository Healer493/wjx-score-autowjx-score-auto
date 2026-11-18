# -*- coding: utf-8 -*-
"""
矢量证书生成器：用 SVG 在原始设计稿坐标系里重绘证书，输出 HTML → PDF/PNG
- 红色主题 = 环球商务英语（Global Business English），级别 A2/B1/B2
- 蓝色主题 = 经典英语（Classic English），级别 Level 1-9
所有元素为矢量，PDF 可无限缩放，300dpi 位图也锐利。
"""
import html
import json
import os
import time

# ---------------------------------------------------------------- 手写签名（矢量）
_HERE = os.path.dirname(os.path.abspath(__file__))
_SIG_FILE = os.path.join(_HERE, "templates", "signature_path.json")


def _load_sig():
    try:
        with open(_SIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


SIG = _load_sig()


def sig_svg(cx, bottom, width, color="#23252a"):
    """把手写签名（已描摹成矢量路径）摆到：水平居中 cx、底边 bottom、宽度 width"""
    if not SIG:
        return ""
    w, h = SIG["w"], SIG["h"]
    s = width / w
    # signature_path.json 里的 d 已经是相对裁剪框左上角的坐标（0..w / 0..h）
    tx, ty = cx - width / 2.0, bottom - h * s
    return (f'<g transform="translate({tx:.2f} {ty:.2f}) scale({s:.5f})" '
            f'fill="{color}"><path d="{SIG["d"]}"/></g>')

# ---------------------------------------------------------------- 通用工具
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def en_date(s):
    """'2026-11-11' -> 'November 11, 2026'"""
    s = (s or "").strip()
    try:
        y, m, d = s[:10].split("-")
        return f"{MONTHS[int(m) - 1]} {int(d)}, {y}"
    except Exception:
        return time.strftime("%B %d, %Y").replace(" 0", " ")


def esc(t):
    return html.escape(str(t or ""), quote=True)


def fit_size(name, base, minimum=9.0):
    """按姓名字长收敛字号，避免撑破横线"""
    n = len(name)
    if n <= 3:
        return base
    return max(minimum, base * (3.0 / n) ** 0.55)


# ---------------------------------------------------------------- 红色（环球商务英语）
def svg_red(name, level_en, date_en, code=""):
    name = (name or "").strip()
    code = (code or "").strip().upper()
    fs = fit_size(name, 15.4)
    if code:
        # 徽章内改成级别（A2 / B1 / B2），多张证书铺开时一眼分辨
        badge_inner = (
            '<text x="390" y="32.0" text-anchor="middle" font-family="Georgia,serif" '
            'font-size="3.5" fill="#a8802f" letter-spacing=".38">LEVEL</text>'
            '<text x="390" y="44.6" text-anchor="middle" font-family="Georgia,Times New Roman,serif" '
            f'font-size="{11.2 if len(code) <= 2 else 9.0:.1f}" font-weight="bold" fill="#8c1a30" '
            f'letter-spacing=".1">{esc(code)}</text>')
    else:
        badge_inner = (
            '<text x="390" y="33.5" text-anchor="middle" font-family="Georgia,serif" font-size="5.2" '
            'fill="#a8802f" letter-spacing=".5">51TALK</text>'
            '<text x="390" y="44" text-anchor="middle" font-family="Georgia,serif" font-size="4.2" '
            'fill="#a8802f" letter-spacing=".6">CERTIFIED</text>')
    return f'''<svg class="sheet" viewBox="0 0 435 308" preserveAspectRatio="none"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="r-band" x1="0" y1="0" x2=".92" y2=".72">
      <stop offset="0" stop-color="#d4738d"/>
      <stop offset=".26" stop-color="#c85268"/>
      <stop offset=".44" stop-color="#b93150"/>
      <stop offset=".62" stop-color="#9d1e39"/>
      <stop offset="1" stop-color="#861630"/>
    </linearGradient>
    <linearGradient id="r-sheen" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".13"/>
      <stop offset=".5" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="1" stop-color="#000000" stop-opacity=".07"/>
    </linearGradient>
    <radialGradient id="r-medal" cx=".38" cy=".32" r=".75">
      <stop offset="0" stop-color="#fdf3d8"/><stop offset=".55" stop-color="#e8c88a"/>
      <stop offset="1" stop-color="#b98f4e"/>
    </radialGradient>
    <linearGradient id="r-foot-a" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#8b0023"/><stop offset="1" stop-color="#680017"/>
    </linearGradient>
    <linearGradient id="r-foot-b" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#d40017"/><stop offset="1" stop-color="#b00114"/>
    </linearGradient>
    <linearGradient id="r-foot-c" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#cd3a67"/><stop offset="1" stop-color="#c02d5c"/>
    </linearGradient>
    <linearGradient id="r-foot" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#78001d"/><stop offset=".34" stop-color="#96001f"/>
      <stop offset=".58" stop-color="#bb0015"/><stop offset=".82" stop-color="#c21b3f"/>
      <stop offset="1" stop-color="#c93a60"/>
    </linearGradient>
    <linearGradient id="r-orn" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#d8b878" stop-opacity=".15"/>
      <stop offset=".5" stop-color="#b8944f"/>
      <stop offset="1" stop-color="#d8b878" stop-opacity=".15"/>
    </linearGradient>
  </defs>

  <rect width="435" height="308" fill="#ffffff"/>

  <!-- 顶部横幅 -->
  <rect width="435" height="78" fill="url(#r-band)"/>
  <rect width="435" height="78" fill="url(#r-sheen)"/>
  <path d="M0 78 H435 V77.2 H0 Z" fill="#f0e6d2"/>
  <rect y="78" width="435" height=".55" fill="#d9c9ac"/>

  <!-- 右上徽章 -->
  <g>
    <circle cx="390" cy="37" r="21.5" fill="url(#r-medal)"/>
    <circle cx="390" cy="37" r="21.5" fill="none" stroke="#b98f4e" stroke-width=".7"/>
    <circle cx="390" cy="37" r="16.4" fill="none" stroke="#c9a765" stroke-width=".55"/>
    <circle cx="390" cy="37" r="13" fill="#fbf1da"/>
    <circle cx="390" cy="37" r="13" fill="none" stroke="#c9a765" stroke-width=".5"/>
    {badge_inner}
  </g>

  <!-- 标题 -->
  <text x="215" y="42.5" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="28.4" fill="#ffffff" letter-spacing="1.35">CERTIFICATE</text>
  <text x="215" y="54.6" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="10.8" fill="#f7ecec" letter-spacing="2.1">OF COMPLETION</text>
  <g stroke="#ffffff" stroke-width=".7" opacity=".82">
    <line x1="118" y1="67.4" x2="146" y2="67.4"/><line x1="284" y1="67.4" x2="312" y2="67.4"/>
  </g>
  <text x="215" y="70.5" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="8.2" fill="#fdf6f6" letter-spacing=".6" font-style="italic">
    With Excellent Performance</text>

  <!-- 金色藤蔓花纹 -->
  <g stroke="#b08c4e" fill="none" stroke-width="1.05" stroke-linecap="round" opacity=".9">
    <path d="M181 102.6 c6.5-4.2 13-3.8 17.4 .8 c-5.6 1.2-6 4.2-.6 4.8"/>
    <path d="M253 102.6 c-6.5-4.2-13-3.8-17.4 .8 c5.6 1.2 6 4.2 .6 4.8"/>
    <path d="M200 103.4 c9.6 2.4 25.4 2.4 35 0"/>
  </g>
  <circle cx="217" cy="103.8" r="1.35" fill="#b08c4e"/>

  <!-- 引导句 -->
  <text x="217.5" y="135.6" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="10.4" font-style="italic" font-weight="bold" fill="#9a1b2f">
    51Talk English hereby certifies that</text>

  <!-- 姓名 -->
  <text x="217.5" y="157.5" text-anchor="middle" font-family="STZhongsong,SimSun,serif"
        font-size="{fs:.2f}" fill="#1f2022" letter-spacing="{1.6 if len(name)<=3 else 0.6}">{esc(name)}</text>
  <line x1="152" y1="162.4" x2="282" y2="162.4" stroke="#c9bda8" stroke-width=".7"/>

  <!-- 正文 -->
  <text x="217.5" y="180.4" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="10.2" font-style="italic" fill="#9a1b2f">
    has successfully met the completion requirements of</text>
  <text x="217.5" y="192.4" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="10.2" font-style="italic" fill="#9a1b2f">the 51Talk Business English {esc(level_en)}</text>

  <!-- 底部三栏标签 -->
  <text x="123" y="235.6" text-anchor="middle" font-family="Georgia,serif" font-size="8.6"
        font-style="italic" fill="#9a1b2f">Date</text>
  <text x="312" y="235.6" text-anchor="middle" font-family="Georgia,serif" font-size="8.6"
        font-style="italic" fill="#9a1b2f">Signature</text>

  <!-- 日期 -->
  <text x="123" y="252.5" text-anchor="middle" font-family="Georgia,serif" font-size="8.4"
        font-style="italic" fill="#8a2130">{esc(date_en)}</text>
  <line x1="82" y1="256.6" x2="164" y2="256.6" stroke="#cbb9a4" stroke-width=".55"/>

  <!-- 中部 Logo -->
  <g>
    <rect x="196" y="240.5" width="42" height="20.5" rx="5.2" fill="#ffd400"/>
    <text x="217" y="253.4" text-anchor="middle" font-family="Arial Black,Arial,sans-serif"
          font-size="11.4" font-weight="bold" fill="#0b57a4" letter-spacing="-.4">51Talk</text>
    <text x="217" y="259.4" text-anchor="middle" font-family="Microsoft YaHei,SimHei,sans-serif"
          font-size="4.1" fill="#0b57a4" letter-spacing=".3">无忧英语</text>
    <g stroke="#efd08a" fill="none" stroke-width=".55" stroke-linecap="round" opacity=".95">
      <path d="M199 266.6 c5-2.6 9-2.6 12 .2"/><path d="M235 266.6 c-5-2.6-9-2.6-12 .2"/>
      <path d="M211 267.4 c4 1.6 8 1.6 12 0"/>
      <circle cx="217" cy="267.2" r=".9" fill="#efd08a" stroke="none"/>
    </g>
  </g>

  <!-- 签名（手写体矢量化，取自经典英语证书原稿） -->
  {sig_svg(312, 254.6, 63)}
  <line x1="276" y1="256.6" x2="348" y2="256.6" stroke="#cbb9a4" stroke-width=".55"/>
  <text x="312" y="264.2" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="4.2" fill="#6b6f78">Jack Huang  |  CEO, 51Talk English</text>

  <!-- 底部色带 -->
  <rect x="0" y="277" width="435" height="31" fill="url(#r-foot)"/>
  <path d="M188 277 L306 277 L190 308 L72 308 Z" fill="#c70016" opacity=".22"/>
</svg>'''


# ---------------------------------------------------------------- 蓝色（经典英语）
def svg_blue(name, level_no, date_en):
    name = (name or "").strip()
    fs = fit_size(name, 23.0)
    lv = str(level_no)
    return f'''<svg class="sheet" viewBox="0 0 720 509" preserveAspectRatio="none"
     xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="b-band" x1="0" y1="0" x2="1" y2=".35">
      <stop offset="0" stop-color="#005083"/><stop offset=".42" stop-color="#0073bb"/>
      <stop offset=".72" stop-color="#00639f"/><stop offset="1" stop-color="#004b7d"/>
    </linearGradient>
    <linearGradient id="b-ribbon" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#c9d1d4"/><stop offset=".28" stop-color="#f0f2f3"/>
      <stop offset=".62" stop-color="#dfe4e6"/><stop offset="1" stop-color="#bcc6c9"/>
    </linearGradient>
    <radialGradient id="b-medal" cx=".4" cy=".34" r=".72">
      <stop offset="0" stop-color="#f6e2b0"/><stop offset=".5" stop-color="#d8b06a"/>
      <stop offset="1" stop-color="#8f6c2c"/>
    </radialGradient>
    <linearGradient id="b-gold" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#efd49a"/><stop offset="1" stop-color="#c39a4a"/>
    </linearGradient>
  </defs>

  <rect width="720" height="509" fill="#ffffff"/>

  <!-- 顶部蓝色横幅（底边为弧线） -->
  <path d="M0 0 H720 V147 C660 143 620 140 550 137 C470 134 380 152 300 160
           C180 166 90 168 0 161 Z" fill="url(#b-band)"/>

  <!-- 左侧缎带 -->
  <g>
    <path d="M46 171 H104 V318 L75 302 L46 318 Z" fill="url(#b-ribbon)"/>
    <path d="M46 171 H104 V318 L75 302 L46 318 Z" fill="none" stroke="#b3bfc3" stroke-width=".8"/>
  </g>
  <!-- 徽章 -->
  <g>
    <circle cx="75" cy="240" r="41" fill="url(#b-gold)"/>
    <circle cx="75" cy="240" r="41" fill="none" stroke="#a9803a" stroke-width="1"/>
    <circle cx="75" cy="240" r="34.5" fill="#2b2a28"/>
    <circle cx="75" cy="240" r="34.5" fill="none" stroke="#c8a35c" stroke-width="1.1"/>
    <circle cx="75" cy="240" r="30" fill="none" stroke="#a8802f" stroke-width=".6"/>
    <text x="75" y="230" text-anchor="middle" font-family="Georgia,serif" font-size="9"
          fill="#e8c982" letter-spacing="1.5">LEVEL</text>
    <text x="75" y="257" text-anchor="middle" font-family="Georgia,serif" font-size="23"
          font-weight="bold" fill="#f2d9a4">{esc(lv)}</text>
  </g>

  <!-- 标题 -->
  <text x="360" y="76" text-anchor="middle" font-family="Georgia,Times New Roman,serif"
        font-size="38" fill="#ffffff" letter-spacing="3.4">CERTIFICATE OF COMPLETION</text>
  <text x="360" y="116" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="21" fill="#ffffff" letter-spacing=".6">With Excellent Performance</text>

  <!-- 正文 -->
  <text x="360" y="226" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="19" font-weight="bold" fill="#2b2b2b">51Talk English hereby certifies that</text>

  <text x="332" y="282" text-anchor="middle" font-family="Microsoft YaHei,SimHei,sans-serif"
        font-size="{fs:.2f}" fill="#3a3a3a" letter-spacing="{3.2 if len(name)<=3 else 1.2}">{esc(name)}</text>
  <line x1="211" y1="294" x2="509" y2="294" stroke="#9aa0a6" stroke-width=".9"/>

  <text x="360" y="322" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="17" fill="#3f3f3f">has successfully met the completion requirements of</text>
  <text x="360" y="347" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="17" fill="#3f3f3f">Classic English proficiency
    <tspan font-weight="bold" fill="#1878bd">level {esc(lv)}</tspan></text>

  <!-- 左下：日期 -->
  <text x="172" y="430" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="16" fill="#3f3f3f">{esc(date_en)}</text>
  <line x1="100" y1="452" x2="245" y2="452" stroke="#9aa0a6" stroke-width="1"/>
  <text x="172" y="466" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="11.5" font-weight="bold" fill="#2b2b2b" letter-spacing=".8">DATE</text>

  <!-- 中部 logo -->
  <g>
    <rect x="321" y="404" width="78" height="42" rx="8" fill="#ffe000"/>
    <text x="360" y="428" text-anchor="middle" font-family="Arial Black,Arial,sans-serif"
          font-size="20" font-weight="bold" fill="#1259a8" letter-spacing="-.6">51Talk</text>
    <text x="360" y="440" text-anchor="middle" font-family="Microsoft YaHei,SimHei,sans-serif"
          font-size="7.2" fill="#1259a8" letter-spacing=".4">无忧英语</text>
  </g>

  <!-- 右下：签名 -->
  <text x="540" y="392" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="10.5" fill="#4a4a4a">Jack Huang , CEO, 51Talk English</text>
  {sig_svg(538, 448, 132)}
  <line x1="447" y1="452" x2="633" y2="452" stroke="#9aa0a6" stroke-width="1"/>
  <text x="540" y="466" text-anchor="middle" font-family="Arial,Helvetica,sans-serif"
        font-size="11.5" font-weight="bold" fill="#2b2b2b" letter-spacing=".8">SIGNATURE</text>
</svg>'''


# ---------------------------------------------------------------- 页面包装
PAGE_TPL = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
  @page {{ size: A4 landscape; margin: 0; }}
  html, body {{ margin: 0; padding: 0; background: #fff; }}
  .page {{
    position: relative; width: 1122px; height: 793px; overflow: hidden;
    background: #fff; page-break-after: always; break-after: page;
  }}
  .page:last-child {{ page-break-after: auto; break-after: auto; }}
  .sheet {{ display: block; width: 1122px; height: 793px; }}
</style></head><body>
{pages}
</body></html>'''


def render_pages(items):
    """items: [{'theme':'red'|'blue','slug':...,'name':...,'level_en':...,'level_no':...,'level_code':...,'date'|'date_en'}]"""
    out = []
    for it in items:
        if it["theme"] == "blue":
            inner = svg_blue(it["name"], it.get("level_no", ""), it.get("date_en") or en_date(it.get("date")))
        else:
            inner = svg_red(it["name"], it.get("level_en", ""),
                            it.get("date_en") or en_date(it.get("date")),
                            it.get("level_code") or "")
        slug = esc(it.get("slug", ""))
        out.append(f'<div class="page" data-slug="{slug}">{inner}</div>')
    return PAGE_TPL.format(title="证书", pages="\n".join(out))


if __name__ == "__main__":
    # 本地预览：三个级别各出一张红版 + 一张蓝版
    demo = [
        {"theme": "red", "name": "王国华", "level_en": "Elementary Level.", "level_code": "A2",
         "date_en": "May 25, 2026"},
        {"theme": "red", "name": "李静", "level_en": "Intermediate Level.", "level_code": "B1",
         "date_en": "October 21, 2026"},
        {"theme": "red", "name": "陈晓", "level_en": "Upper-Intermediate Level.", "level_code": "B2",
         "date_en": "November 11, 2026"},
        {"theme": "blue", "name": "徐迪", "level_no": 9, "date_en": "October 21, 2026"},
    ]
    open("preview_svg.html", "w", encoding="utf-8").write(render_pages(demo))
    print("wrote preview_svg.html")
