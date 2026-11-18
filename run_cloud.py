# -*- coding: utf-8 -*-
"""
GitHub Actions 入口：抓数 -> 出证书 -> 打包 -> 落到 docs/ 供 Pages 发布。

与 run_all.py 的区别：去掉 publish_targets.py（那一步依赖 WorkBuddy 内网认证和
本机 dws 命令，GitHub Actions 里不存在），发布交给 GitHub Pages 的 docs/ 目录。

用法：python run_cloud.py
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
DOCS = BASE / "docs"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def step(name, script, timeout=1200):
    log(f"▶ {name}")
    r = subprocess.run([sys.executable, script], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    # 把子进程关键输出透出来，方便在 Actions 日志里排错
    for line in out.splitlines()[-25:]:
        print("   " + line)
    if r.returncode != 0:
        raise SystemExit(f"[x] {name} 失败（exit {r.returncode}）\n{out[-2000:]}")
    log(f"✓ {name} 完成")


def main():
    key = (os.environ.get("WJX_API_KEY") or "").strip()
    if not key:
        raise SystemExit("[x] 缺少 WJX_API_KEY，请在仓库 Secrets 里配置")

    # 上一版统计，用于算增量
    prev = {}
    prev_file = DOCS / "run.json"
    if prev_file.exists():
        try:
            prev = json.loads(prev_file.read_text(encoding="utf-8")).get("by_level", {}) or {}
        except Exception:
            pass
    if prev:
        log(f"上一版：{prev}")

    DOCS.mkdir(exist_ok=True)
    step("抓数据 + 算分 + 出页面", "update.py")
    step("生成证书（≥80 分）", "cert.py")
    step("打包单文件版", "pack_html.py")

    single = BASE / "成绩查询_单文件版.html"
    if not single.exists():
        raise SystemExit("[x] 未找到单文件版页面")
    shutil.copy2(single, DOCS / "index.html")

    raw = json.loads((BASE / "data_raw.json").read_text(encoding="utf-8"))
    cur = {k: int(v.get("answer_count") or 0)
           for k, v in (raw.get("levels") or {}).items()}
    total = sum(cur.values())

    delta = {}
    for k in set(cur) | set(prev):
        d = cur.get(k, 0) - prev.get(k, 0)
        if d:
            delta[k] = d

    cert_list = []
    idx = BASE / "证书" / "index.json"
    if idx.exists():
        try:
            for it in json.loads(idx.read_text(encoding="utf-8")):
                cert_list.append(f"{it.get('name')}（{it.get('level')} · {it.get('score')} 分）")
        except Exception:
            pass

    rec = {
        "at": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "total": total,
        "by_level": cur,
        "certs": len(cert_list),
        "cert_list": cert_list,
        "delta": delta,
    }
    (DOCS / "run.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    log("──────── 本次结果 ────────")
    log(f"答卷 {total} 份  " + "  ".join(f"{k}={v}" for k, v in cur.items()))
    if delta:
        log("新增：" + "  ".join(f"{k}+{v}" for k, v in delta.items()))
    log(f"证书 {len(cert_list)} 张：" + ("、".join(cert_list) if cert_list else "无"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
