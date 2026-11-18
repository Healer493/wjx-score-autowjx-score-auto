# -*- coding: utf-8 -*-
"""
把 成绩查询.html 打成「单文件自包含版」：证书 PNG/PDF 全部 base64 内嵌，
点击时在【页面内弹层】显示，不再新开窗口、不依赖任何外部相对路径。

为什么要这么改（2026-11-16 踩坑）：
  钉钉知识库 / 资料库把 HTML 存成单个 web 节点，会把 a[href="证书/x.png"]
  重写成 https://default.kinfra.myqcloud.com/<token>/证书/x.png，
  而证书文件并没有上传到那儿 → 点开 404「错误提醒」。
  旧方案用「捕获点击 + window.open(blob)」拦截，链接被重写后匹配不上，直接漏成 404；
  且 blob 顶层导航在沙箱 iframe 里也可能被拦。
  新方案：不依赖 href 真假值（按 decodeURIComponent 后的 '证书/' 尾部取文件名，
  重写成绝对 URL 也能取到），一律 preventDefault，在页内 <img src="data:..."> 展示。

用法：python pack_html.py [源html] [输出html]
  默认：成绩查询.html -> 成绩查询_单文件版.html
  也可对「资料库托管的线上版」就地注入（保留平台注入的 page_common 等脚本）：
  python pack_html.py <work_dir>/成绩查询.html <work_dir>/成绩查询.html
"""
import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
SRC = Path(args[0]) if args else HERE / "成绩查询.html"
OUT = Path(args[1]) if len(args) > 1 else HERE / "成绩查询_单文件版.html"
CERT_DIR = HERE / "证书"

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".pdf": "application/pdf", ".webp": "image/webp"}

# 1. 收集证书文件 → base64，按「同名不同后缀」归到一个 key 下
certs = {}
if CERT_DIR.exists():
    for f in sorted(CERT_DIR.iterdir()):
        if not f.is_file() or f.name == "index.json":
            continue
        ext = f.suffix.lower()
        if ext not in MIME:
            continue
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        rec = certs.setdefault(f.stem, {})
        rec[ext.lstrip(".")] = f"data:{MIME[ext]};base64,{b64}"
        print(f"  内嵌 {f.name:<30} {f.stat().st_size/1024:>8.1f} KB")

html = SRC.read_text(encoding="utf-8")

# 2. 页内弹层 + 拦截逻辑
INJECT = r"""
<style id="__cert_css__">
#certLb{position:fixed;inset:0;z-index:99999;display:none;background:rgba(13,16,20,.93);
  -webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
#certLb.on{display:flex;flex-direction:column}
#certLb .clb-bar{flex:0 0 auto;display:flex;align-items:center;gap:8px;padding:12px 16px;
  color:#f2f4f7;font:500 14px/1 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
#certLb .clb-t{font-size:14px;font-weight:600;letter-spacing:.3px;max-width:46vw;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#certLb .clb-sp{flex:1 1 auto}
#certLb .clb-b{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;
  min-height:34px;appearance:none;border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.08);
  color:#eef1f5;border-radius:8px;padding:0 13px;font-size:13px;cursor:pointer;text-decoration:none;
  font-family:inherit;white-space:nowrap;line-height:1}
#certLb .clb-b:hover{background:rgba(255,255,255,.18)}
#certLb .clb-b.primary{background:#c8a35a;border-color:#c8a35a;color:#1a1c20;font-weight:600}
#certLb .clb-body{flex:1 1 auto;overflow:auto;display:flex;align-items:flex-start;justify-content:center;
  padding:0 16px 10px}
#certLb img{display:block;width:100%;max-width:1600px;height:auto;border-radius:6px;
  box-shadow:0 18px 60px rgba(0,0,0,.55);background:#fff}
#certLb .clb-tip{flex:0 0 auto;text-align:center;color:rgba(255,255,255,.52);font-size:12px;
  padding:0 16px 14px;line-height:1.6}
@media(max-width:700px){
  #certLb .clb-bar{flex-wrap:wrap;padding:10px 12px}
  #certLb .clb-t{width:100%;max-width:none}
  #certLb .clb-b{flex:1 1 auto;text-align:center;padding:9px 8px;font-size:12px}
  #certLb .clb-body{padding:0 8px 8px}
}
</style>
<div id="certLb" role="dialog" aria-modal="true" aria-label="证书预览">
  <div class="clb-bar">
    <span class="clb-t" id="clbT">证书</span><span class="clb-sp"></span>
    <button type="button" class="clb-b" data-z="out" title="缩小">－</button>
    <button type="button" class="clb-b" data-z="in" title="放大">＋</button>
    <button type="button" class="clb-b" data-z="fit">适应宽度</button>
    <a class="clb-b primary" id="clbDl" download>下载图片</a>
    <a class="clb-b" id="clbPdf" download>打印版 PDF</a>
    <button type="button" class="clb-b" id="clbX">关闭</button>
  </div>
  <div class="clb-body"><img id="clbImg" alt="证书"></div>
  <div class="clb-tip">电脑端可右键图片「另存为」；手机端长按图片保存。需要印刷请用「打印版 PDF」（纯矢量，放大不失真）。</div>
</div>
<script id="__cert_inline__">
/* 单文件版：证书已 base64 内嵌，页内弹层预览。
   链接无论是 "证书/x.png" 还是被平台重写成的绝对 URL，都按末尾 '证书/' 后取文件名。 */
var CERT_B64 = __CERT_MAP__;
(function () {
  var LB = document.getElementById('certLb');
  if (!LB) return;
  var IMG = document.getElementById('clbImg');
  var T = document.getElementById('clbT');
  var DL = document.getElementById('clbDl');
  var PDF = document.getElementById('clbPdf');
  var zoom = 1;

  function certName(href) {
    if (!href) return '';
    try { href = decodeURIComponent(href); } catch (e) {}
    var i = href.lastIndexOf('证书/');
    if (i < 0) return '';
    var rest = href.slice(i + 3).split(/[?#]/)[0].replace(/^\/+/, '');
    return rest;
  }
  function pick(name) {
    if (!name) return null;
    var n = String(name).replace(/\.[^.]+$/, '').toLowerCase();
    for (var k in CERT_B64) {
      if (k.toLowerCase() === n) return k;
    }
    return null;
  }
  function setZoom(z) {
    zoom = Math.min(4, Math.max(0.25, z));
    IMG.style.width = (zoom * 100).toFixed(0) + '%';
  }
  function open(name) {
    var key = pick(name);
    if (!key) {
      if (window.dtkToast) dtkToast('未找到证书文件：' + name, 3400);
      else alert('未找到证书文件：' + name);
      return;
    }
    var rec = CERT_B64[key] || {};
    IMG.src = rec.png || rec.jpg || rec.jpeg || rec.webp || '';
    T.textContent = '证书 · ' + key;
    DL.href = IMG.src;
    DL.setAttribute('download', key + (rec.png ? '.png' : ''));
    if (rec.pdf) {
      PDF.style.display = '';
      PDF.href = rec.pdf;
      PDF.setAttribute('download', key + '.pdf');
    } else {
      PDF.style.display = 'none';
    }
    setZoom(1);
    LB.classList.add('on');
    LB.scrollTop = 0;
    document.documentElement.style.overflow = 'hidden';
  }
  function close() {
    LB.classList.remove('on');
    IMG.removeAttribute('src');
    document.documentElement.style.overflow = '';
  }

  /* 捕获阶段拦截：先判断是否证书链接，命中就彻底接管 */
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a) return;
    var n = certName(a.getAttribute('href') || '');
    if (!n) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    open(n);
  }, true);

  if (LB.querySelector) {
    LB.addEventListener('click', function (e) {
      var z = e.target.getAttribute && e.target.getAttribute('data-z');
      if (z === 'in') setZoom(zoom * 1.25);
      else if (z === 'out') setZoom(zoom / 1.25);
      else if (z === 'fit') setZoom(1);
    });
    document.getElementById('clbX').addEventListener('click', close);
    LB.addEventListener('click', function (e) { if (e.target === LB) close(); });
    document.addEventListener('keydown', function (e) {
      if (!LB.classList.contains('on')) return;
      if (e.key === 'Escape') close();
      if (e.key === '+' || e.key === '=') setZoom(zoom * 1.25);
      if (e.key === '-') setZoom(zoom / 1.25);
    });
  }
})();
</script>
"""

html_out = html.replace("</body>", INJECT.replace("__CERT_MAP__", json.dumps(certs, ensure_ascii=False)) + "</body>")

OUT.write_text(html_out, encoding="utf-8")
print(f"\n[ok] {OUT.name}  {len(html_out)/1024/1024:.2f} MB  "
      f"(原 {len(html)/1024:.0f} KB · 内嵌证书 {len(certs)} 份)")
