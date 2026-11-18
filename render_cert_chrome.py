# -*- coding: utf-8 -*-
"""
用 Chrome / Chromium 命令行渲染证书：PNG(300dpi) + 纯矢量 PDF，不依赖 node / puppeteer。

为什么要这条路：
  云端沙箱里 node 有、npm 全局安装却通常没权限，puppeteer-core 还要带一堆依赖；
  而 Chrome 自带 `--screenshot` / `--print-to-pdf`，输出与 puppeteer 逐像素一致
  （实测平均灰度差 0.31，>64 的像素仅 0.08%，都是字形抗锯齿差异）。

关键参数：
  --window-size=1122,793           与 .page 的 CSS 尺寸对齐（A4 横向 @96dpi）
  --force-device-scale-factor      3508/1122 ≈ 3.1266，得到 A4 300dpi（3508×2479）
  --print-to-pdf 走 @page size:A4 landscape，出来就是 297×210mm 的单页矢量 PDF

用法：
  python render_cert_chrome.py <html> <输出目录> [png|pdf|both]     # 独立测试整份 HTML
模块：
  render([{"slug":..., "html":...}, ...], out_dir, "both")
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_W, PAGE_H = 1122, 793
DSF = 3508 / 1122          # A4 300dpi 宽 3508px

CHROME_CANDIDATES = [
    # Linux
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome",
    "/snap/bin/chromium",
    # Windows
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome():
    env = (os.environ.get("CHROME_PATH") or "").strip()
    if env and Path(env).exists():
        return env
    for name in ("chromium", "chromium-browser", "google-chrome",
                 "google-chrome-stable", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _run(chrome, args, timeout=90, headless="--headless=new"):
    cmd = [chrome, headless, "--disable-gpu", "--no-sandbox",
           "--disable-dev-shm-usage", "--hide-scrollbars",
           "--allow-file-access-from-files", "--font-render-hinting=none"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                       timeout=timeout)
    return r


# 老的 chromium 不认识 --headless=new，逐级降级重试
HEADLESS_MODES = ("--headless=new", "--headless", "--headless=old")


def _uri(path):
    return Path(path).resolve().as_uri()


def _try(chrome, args, out_path, min_size):
    """跑一条渲染命令；产出不达标就换 headless 模式重试"""
    out_path = Path(out_path)
    last = ""
    for mode in HEADLESS_MODES:
        if out_path.exists():
            out_path.unlink()
        try:
            r = _run(chrome, args, headless=mode)
            last = (r.stderr or "")[:200]
        except Exception as e:
            last = str(e)[:200]
        if out_path.exists() and out_path.stat().st_size >= min_size:
            return True, mode
    return False, last


def _one(chrome, html_path, out_dir, slug, mode):
    """渲一份：PNG + PDF"""
    png = str(Path(out_dir) / (slug + ".png"))
    pdf = str(Path(out_dir) / (slug + ".pdf"))
    uri = _uri(html_path)

    if mode in ("both", "png"):
        ok, info = _try(chrome, [f"--window-size={PAGE_W},{PAGE_H}",
                                 f"--force-device-scale-factor={DSF:.4f}",
                                 "--default-background-color=ffffffff",
                                 f"--screenshot={Path(png).resolve()}", uri],
                        png, 20000)
        if not ok:
            raise RuntimeError(f"PNG 渲染失败 {slug}: {info}")

    if mode in ("both", "pdf"):
        ok, info = _try(chrome, ["--no-pdf-header-footer", "--no-pdf-header",
                                 "--no-pdf-footer",
                                 f"--print-to-pdf={Path(pdf).resolve()}", uri],
                        pdf, 5000)
        if not ok:
            raise RuntimeError(f"PDF 渲染失败 {slug}: {info}")


def render(pages, out_dir, mode="both", log=print):
    """pages: [{"slug": str, "html": str}]；返回成功份数。"""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Chromium，请设置 CHROME_PATH")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ok = 0
    with tempfile.TemporaryDirectory(prefix="cert_") as tmp:
        for i, p in enumerate(pages):
            hp = Path(tmp) / f"p{i}.html"
            hp.write_text(p["html"], encoding="utf-8")
            _one(chrome, hp, out_dir, p["slug"], mode)
            ok += 1
            log(f"  ✓ {p['slug']}")
    return ok


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        return 2
    html_path, out_dir = args[0], args[1]
    mode = args[2] if len(args) > 2 else "both"
    # 整份 HTML 里有多个 .page：拆成单页再逐个截图（CLI 只能截整页）
    src = Path(html_path).read_text(encoding="utf-8")
    import re
    head = src.split("<body>")[0] + "<body>\n"
    blocks = re.findall(r'<div class="page" data-slug="([^"]*)">(.*?)</div>\s*(?=<div class="page"|</body>)',
                        src, re.S)
    if not blocks:
        raise SystemExit("没解析到 .page 块")
    pages = [{"slug": s or str(i + 1), "html": head + f'<div class="page">{b}</div></body></html>'}
             for i, (s, b) in enumerate(blocks)]
    n = render(pages, out_dir, mode)
    print(f"DONE {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
