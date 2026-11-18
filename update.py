# -*- coding: utf-8 -*-
"""
一键更新：拉取问卷星 A2/B1/B2 结构 + 答卷，生成单文件成绩查询页
用法: python update.py
产出: 成绩查询.html（双击即可打开，无需联网、无需登录问卷星）
"""
import json, os, subprocess, sys, time, re, html, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import wjx_client
# 本地兜底：云端/服务器上请用环境变量 WJX_API_KEY（优先），不要放文件
KEY_FILE = os.environ.get("WJX_KEY_FILE") or r"C:\Users\wujian06\Desktop\问卷星API.md"
OUT_HTML = os.path.join(BASE, "成绩查询.html")
RAW_JSON = os.path.join(BASE, "data_raw.json")

LEVELS = {
    "A2": {"vid": 397630883, "url": "https://ks.wjx.com/vm/PHGtM9y.aspx", "series": "business"},
    "B1": {"vid": 397630876, "url": "https://ks.wjx.com/vm/tEoMhXG.aspx", "series": "business"},
    "B2": {"vid": 397630799, "url": "https://ks.wjx.com/vm/wZxzBXC.aspx", "series": "business"},
}
# 课程体系 → 证书主题（红=环球商务英语 / 蓝=经典英语）
SERIES = {
    "business": {"name": "环球商务英语", "cls": "biz"},
    "classic": {"name": "经典英语", "cls": "cls"},
}
# 级别身份：英文全称 + 视觉色（环球体系用红的深浅递进，级别越高越深）
LEVEL_INFO = {
    "A2": {"en": "Elementary",         "cn": "初级",   "c": "#c25d72", "tint": "#fdf1f4"},
    "B1": {"en": "Intermediate",       "cn": "中级",   "c": "#a01f38", "tint": "#fbeaee"},
    "B2": {"en": "Upper-Intermediate", "cn": "中高级", "c": "#6a1322", "tint": "#f6e7ea"},
}


def lv_info(code):
    d = LEVEL_INFO.get(code) or {}
    return {"en": d.get("en", ""), "cn": d.get("cn", ""), "c": d.get("c", "#1b4f9c")}

PAGE_SIZE = 50
PASS, EXCELLENT = 60, 80


def get_key():
    """优先环境变量（云端 / 定时任务），其次本地 key 文件。"""
    k = (os.environ.get("WJX_API_KEY") or "").strip()
    if k:
        return k
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return open(KEY_FILE, encoding=enc).read().strip()
        except Exception:
            continue
    raise SystemExit("未设置环境变量 WJX_API_KEY，且读取 key 文件失败: " + KEY_FILE)


def run_cli(args, key):
    """取问卷星数据。

    默认走纯 Python HTTP（wjx_client，不依赖 node / wjx-cli），
    这样云端定时任务不用 npm 全局安装；本地想用 CLI 可设 WJX_MODE=cli，
    设 WJX_MODE=api 则不允许退回 CLI。
    """
    mode = (os.environ.get("WJX_MODE") or "").strip().lower()
    if mode != "cli":
        try:
            return wjx_client.run_cli_style(args, key)
        except wjx_client.WjxError as e:
            raise RuntimeError(str(e))          # 业务错误，重试无意义
        except Exception as e:
            if mode == "api":
                raise RuntimeError(f"问卷星接口调用失败：{e}")
            print(f"  ! 接口直连失败（{e}），退回 wjx-cli")

    env = dict(os.environ)
    env["WJX_API_KEY"] = key
    env.setdefault("NO_COLOR", "1")
    args = [str(a) for a in args]
    if os.name == "nt":
        p = subprocess.run("wjx " + " ".join(args), shell=True, capture_output=True,
                           env=env, encoding="utf-8", errors="replace")
    else:
        exe = shutil.which("wjx")
        if not exe:
            raise RuntimeError("未找到 wjx 命令，请先执行：npm i -g wjx-cli")
        p = subprocess.run([exe] + args, capture_output=True,
                           env=env, encoding="utf-8", errors="replace")
    out = (p.stdout or "").strip()
    if not out:
        raise RuntimeError("wjx 无输出: " + " ".join(args) + " | " + (p.stderr or "")[:200])
    try:
        return json.loads(out)
    except Exception:
        i, j = out.find("{"), out.rfind("}")
        if i >= 0 and j > i:
            return json.loads(out[i:j + 1])
        raise RuntimeError("wjx 输出非 JSON: " + out[:200])


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def clean_option(t):
    """选项文本去掉开头字母：'A. The workshops' -> ('A', 'The workshops')"""
    t = (t or "").strip()
    m = re.match(r"^([A-Za-z])[\.\．、\)]\s*(.*)$", t)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return "", t


def parse_parsing(q_parsing):
    """把后台 _ceshiDesc 拆成 {answer_text, explanation}"""
    if not q_parsing:
        return "", ""
    raw = q_parsing.replace("<br/>", "<br>").replace("<br />", "<br>")
    parts = [p for p in re.split(r"<br\s*/?>", raw) if p.strip()]
    ans, exp = "", []
    for p in parts:
        txt = strip_tags(p)
        if not txt:
            continue
        if (txt.startswith("答案") or txt.startswith("正确答案")) and not ans:
            ans = re.sub(r"^(正确答案|答案)\s*[:：]\s*", "", txt).strip()
        elif txt.startswith("解析") and not exp:
            exp.append(re.sub(r"^解析\s*[:：]\s*", "", txt).strip())
        else:
            exp.append(txt)
    return ans, " ".join([e for e in exp if e]).strip()


def fetch_structure(level, vid, key):
    d = run_cli(["survey", "get", "--vid", str(vid), "--format", "json"], key)
    if not d.get("ok"):
        raise RuntimeError(f"{level} 结构读取失败: {d.get('error')}")
    data = d["data"]
    questions = []
    for q in data.get("questions", []):
        if q.get("q_type") != 3:      # 只要单选
            continue
        opts, correct = [], []
        for it in q.get("items", []) or []:
            letter, text = clean_option(it.get("item_title"))
            if not letter:
                letter = chr(ord("A") + len(opts))
            opts.append({"letter": letter, "text": text})
            if it.get("item_selected"):
                correct.append(letter)
        a_txt, expl = parse_parsing(q.get("q_parsing"))
        questions.append({
            "q_index": q.get("q_index"),
            "stem": strip_tags(q.get("q_title")),
            "options": opts,
            "correct": correct,
            "score": int(float(q.get("q_score") or 0)),
            "parsing_answer": a_txt,
            "explanation": expl,
        })
    questions.sort(key=lambda x: x.get("q_index") or 0)
    for i, q in enumerate(questions):
        q["no"] = i + 1
    return {"title": data.get("title"), "total_score": data.get("total_score"),
            "questions": questions}


def fetch_answers(level, vid, key, log=print):
    all_answers, page = {}, 1
    while True:
        d = run_cli(["response", "query", "--vid", str(vid), "--page_index", str(page),
                     "--page_size", str(PAGE_SIZE), "--format", "json"], key)
        if not d.get("ok"):
            raise RuntimeError(f"{level} 答卷读取失败: {d.get('error')}")
        data = d["data"]
        total = data.get("total_count", 0)
        answers = data.get("answers") or {}
        if not answers:
            break
        all_answers.update(answers)
        log(f"   第 {page} 页 {len(answers)} 条（累计 {len(all_answers)}/{total}）")
        if len(all_answers) >= total or len(answers) < PAGE_SIZE:
            break
        page += 1
        if page > 500:
            break
    return all_answers


def build_records(level, struct, answers):
    """答卷 -> 页面需要的扁平记录（含逐题对错）"""
    by_index = {q["q_index"]: q for q in struct["questions"]}
    records = []
    for jid, a in answers.items():
        items = a.get("answer_items") or {}
        candidate, details, right = "", [], 0
        earned = 0
        for qi, v in items.items():
            try:
                qi = int(qi if isinstance(qi, int) else v.get("q_index"))
            except Exception:
                continue
            if qi not in by_index:
                if v.get("answer_text"):
                    candidate = str(v["answer_text"]).strip()
                continue
            q = by_index[qi]
            chosen = []
            for idx in (v.get("item_index") or []):
                try:
                    chosen.append(chr(ord("A") + int(idx) - 1))
                except Exception:
                    pass
            if not chosen and v.get("answer_text"):
                chosen = [str(v["answer_text"]).strip()[:1].upper()]
            ok = sorted(chosen) == sorted(q["correct"])
            if ok:
                right += 1
                earned += q["score"]
            details.append({
                "no": q["no"], "stem": q["stem"],
                "chosen": chosen, "correct": q["correct"],
                "ok": ok, "score": q["score"],
                "options": q["options"],
                "explanation": q["explanation"],
            })
        details.sort(key=lambda d: d["no"])
        score = a.get("score")
        try:
            score = float(score)
        except Exception:
            score = float(earned)
        records.append({
            "jid": str(jid),
            "level": level,
            "name": candidate or "（未填写）",
            "score": score,
            "calc_score": earned,
            "total": float(a.get("total_score") or struct.get("total_score") or 100),
            "right": right,
            "count": len(details),
            "seconds": int(a.get("answer_seconds") or 0),
            "submit_time": a.get("submit_time") or "",
            "province": ((a.get("province") or "") + " " + (a.get("city") or "")).strip(),
            "source": a.get("source") or "",
            "missing": len(by_index) - len(details),
            "details": details,
        })
    records.sort(key=lambda r: r["submit_time"], reverse=True)
    return records


def main():
    key = get_key()
    out = {"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "levels": {}}
    print("读取问卷结构与答卷...")
    for level, info in LEVELS.items():
        print(f"  [{level}] vid={info['vid']}")
        struct = fetch_structure(level, info["vid"], key)
        answers = fetch_answers(level, info["vid"], key)
        recs = build_records(level, struct, answers)
        out["levels"][level] = {
            "vid": info["vid"], "url": info["url"],
            "title": struct["title"], "total_score": struct["total_score"],
            "questions": struct["questions"],
            "records": recs,
            "answer_count": len(recs),
            "series": info.get("series", "business"),
            "series_name": SERIES.get(info.get("series", "business"), {}).get("name", "环球商务英语"),
            "series_cls": SERIES.get(info.get("series", "business"), {}).get("cls", "biz"),
            "level_en": lv_info(level)["en"],
            "level_cn": lv_info(level)["cn"],
            "level_color": lv_info(level)["c"],
            "level_order": list(LEVELS).index(level),
        }
        print(f"    -> {len(recs)} 份答卷，{len(struct['questions'])} 题")

    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- 证书：≥80 分自动生成 ----
    cert_items = []
    try:
        import cert as cert_mod
        print("\n生成优秀证书（≥80 分）...")
        cert_items = cert_mod.main() or []
        cmap = {x["key"]: x for x in cert_items}
        for lv, L in out["levels"].items():
            for r in L["records"]:
                r["cert"] = cmap.get(f"{lv}:{r['jid']}")
    except Exception as e:
        print("证书生成跳过（不影响成绩页）:", e)

    out["cert_count"] = len(cert_items)
    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    html_str = render(out)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_str)
    n = sum(v["answer_count"] for v in out["levels"].values())
    print(f"\n完成：{OUT_HTML}")
    print(f"共 {n} 份答卷，页面大小 {os.path.getsize(OUT_HTML)/1024:.0f} KB")


# ---------------------------------------------------------------- 页面渲染
def render(data):
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("/*__DATA__*/null", payload, 1)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>环球商务英语级别测试 · 成绩查询</title>
<style>
  :root{
    --bg:#f5f6f8; --card:#ffffff; --line:#e3e6ec; --line2:#eef0f4;
    --ink:#1a1f2b; --ink2:#5a6478; --ink3:#8e97a8;
    --blue:#1b4f9c; --blue-l:#e8f0fb; --gold:#b8892b; --gold-l:#fbf3e2;
    --green:#1a7f5a; --green-l:#e7f5ef; --red:#c0392b; --red-l:#fbeceb;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--ink);
    font:14px/1.6 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    -webkit-font-smoothing:antialiased;padding:0 0 60px}
  .wrap{max-width:1180px;margin:0 auto;padding:0 20px}
  /* header */
  header{background:#fff;border-bottom:1px solid var(--line);padding:22px 0 18px;margin-bottom:20px}
  .h-top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap}
  h1{font-size:21px;font-weight:600;letter-spacing:.2px}
  h1 .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--gold);
    margin:0 10px 3px 0;vertical-align:middle}
  .meta{font-size:12px;color:var(--ink3);margin-top:4px}
  .btn{border:1px solid var(--line);background:#fff;color:var(--ink2);border-radius:6px;
    padding:7px 14px;font-size:13px;cursor:pointer;transition:.15s;white-space:nowrap}
  .btn:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-l)}
  .btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
  .btn.primary:hover{background:#16407e}
  /* papers */
  .papers{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
  .paper{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px;
    display:flex;align-items:center;gap:12px}
  .paper .lv{font-size:13px;font-weight:700;color:#fff;letter-spacing:.4px;text-align:center;
    min-width:38px;background:var(--blue);border-radius:5px;padding:5px 9px;flex-shrink:0}
  .paper .lv .e{display:block;font-size:9px;font-weight:500;opacity:.9;letter-spacing:0;
    margin-top:1px;white-space:nowrap}
  .paper .sn{font-size:10px;color:var(--ink3);margin-top:2px;letter-spacing:.2px}
  .paper .info{min-width:0;flex:1}
  .paper .u{font-size:12px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .paper .u:hover{color:var(--blue)}
  .paper .c{font-size:11px;color:var(--ink3);margin-top:1px}
  .paper button{border:1px solid var(--line);background:#fff;color:var(--ink3);border-radius:5px;
    padding:5px 10px;font-size:11px;cursor:pointer;flex-shrink:0;transition:.15s}
  .paper button:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-l)}
  /* kpi */
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .kpi .k{font-size:12px;color:var(--ink3);letter-spacing:.3px}
  .kpi .v{font-size:24px;font-weight:600;margin-top:2px;font-variant-numeric:tabular-nums}
  .kpi .v small{font-size:12px;font-weight:400;color:var(--ink3);margin-left:3px}
  .kpi.gold .v{color:var(--gold)} .kpi.blue .v{color:var(--blue)}
  /* panel */
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:18px}
  .panel-h{padding:14px 18px;border-bottom:1px solid var(--line2);display:flex;
    align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
  .panel-t{font-size:14px;font-weight:600}
  .panel-t span{font-weight:400;color:var(--ink3);font-size:12px;margin-left:8px}
  /* tabs + filters */
  .bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:14px 18px;
    border-bottom:1px solid var(--line2)}
  .tabs{display:flex;gap:4px;background:var(--bg);padding:3px;border-radius:7px}
  .tab{border:0;background:transparent;padding:6px 16px;border-radius:5px;font-size:13px;
    color:var(--ink2);cursor:pointer;font-weight:500;transition:.15s}
  .tab.on{background:#fff;color:var(--blue);box-shadow:0 1px 3px rgba(20,40,80,.12)}
  .tab u{text-decoration:none;color:var(--ink3);font-weight:400;margin-left:4px;font-size:11px}
  input[type=search],select{border:1px solid var(--line);border-radius:6px;padding:7px 11px;
    font-size:13px;color:var(--ink);background:#fff;outline:none;font-family:inherit}
  input[type=search]{width:210px}
  input[type=search]:focus,select:focus{border-color:var(--blue)}
  .spacer{flex:1}
  /* charts */
  .charts{display:grid;grid-template-columns:1.6fr 1fr;gap:0;border-bottom:1px solid var(--line2)}
  .chart{padding:16px 18px}
  .chart+.chart{border-left:1px solid var(--line2)}
  .chart-t{font-size:12px;color:var(--ink3);margin-bottom:14px;letter-spacing:.3px;
    display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
  .lg{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--ink2)}
  .lg i{display:inline-block;width:8px;height:8px;border-radius:2px}
  .lg + .lg{margin-left:10px}
  .hist{display:flex;align-items:flex-end;gap:8px;height:120px}
  .hbar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px;height:100%}
  .hbar .n{font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums}
  .hbar .bwrap{width:100%;display:flex;flex-direction:column;justify-content:flex-end;gap:1px}
  .hbar .bwrap i{display:block;width:100%;min-height:2px}
  .hbar .bwrap i:first-child{border-radius:3px 3px 0 0}
  .hbar .l{font-size:11px;color:var(--ink3);margin-top:2px}
  .lvlist{display:flex;flex-direction:column;gap:12px;justify-content:center;height:120px}
  .lvrow{display:grid;grid-template-columns:42px 1fr 48px;align-items:center;gap:10px;font-size:12px}
  .lvrow .lb{color:var(--ink2);font-weight:600;white-space:nowrap}
  .lvrow .track{display:block;height:10px;background:#eceff4;border-radius:5px;overflow:hidden;
    box-shadow:inset 0 0 0 1px rgba(20,40,80,.04)}
  .lvrow .fill{display:block;height:10px;background:linear-gradient(90deg,#2b62b8,#1b4f9c);
    border-radius:5px;transition:.3s;min-width:2px}
  .lvrow .fill.na{background:repeating-linear-gradient(45deg,#e6e9ef,#e6e9ef 4px,#f2f4f8 4px,#f2f4f8 8px);min-width:100%}
  .lvrow .vv{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
  .kpi.lvk{position:relative;overflow:hidden}
  .kpi .k .lvtag{padding:1px 6px;font-size:10px;margin-right:5px;vertical-align:1px}
  .tab .kdot{margin-right:5px}
  /* table */
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;font-weight:500;color:var(--ink3);font-size:12px;
    padding:10px 14px;border-bottom:1px solid var(--line2);white-space:nowrap;
    cursor:pointer;user-select:none;position:relative}
  th:hover{color:var(--blue)}
  th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
  th.sorted::after{content:" ↓";color:var(--blue)}
  th.sorted.asc::after{content:" ↑"}
  tbody tr{border-bottom:1px solid var(--line2);cursor:pointer;transition:.12s}
  tbody tr:hover{background:#fafbfd}
  td{padding:11px 14px;vertical-align:middle}
  .nm{font-weight:500}
  .sub{font-size:11px;color:var(--ink3);margin-top:1px}
  .lvtag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;
    background:var(--blue);color:#fff;letter-spacing:.5px}
  .lvtag.k-A2{background:#c25d72} .lvtag.k-B1{background:#a01f38} .lvtag.k-B2{background:#6a1322}
  .lvtag.biz{background:#a81f39} .lvtag.cls{background:#0d5b96}
  .lven{font-size:11px;color:var(--ink2);margin-left:6px;letter-spacing:.2px;white-space:nowrap}
  th.lvcol{width:118px}
  .tag{white-space:nowrap}
  .kdot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:5px;vertical-align:1px}
  .sersw{display:inline-block;width:7px;height:7px;border-radius:2px;margin-right:5px;vertical-align:1px}
  .sersw.biz{background:#a81f39} .sersw.cls{background:#0d5b96}
  .sc{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
  .tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:500}
  .tag.ex{background:var(--gold-l);color:var(--gold)}
  .tag.pa{background:var(--green-l);color:var(--green)}
  .tag.fa{background:var(--red-l);color:var(--red)}
  .certbtn{display:inline-block;padding:3px 9px;border-radius:4px;font-size:11px;font-weight:600;
    background:var(--gold-l);color:var(--gold);border:1px solid #eddfc0;text-decoration:none;
    white-space:nowrap;transition:.15s}
  .certbtn:hover{background:var(--gold);color:#fff;border-color:var(--gold)}
  .certbtn.biz{background:#fdf1f4;color:#a81f39;border-color:#f0d5dc}
  .certbtn.biz:hover{background:#a81f39;color:#fff;border-color:#a81f39}
  .certbtn.cls{background:#eef5fc;color:#0d5b96;border-color:#cfe2f3}
  .certbtn.cls:hover{background:#0d5b96;color:#fff;border-color:#0d5b96}
  .mini{height:5px;width:64px;background:var(--bg);border-radius:3px;overflow:hidden;
    display:inline-block;vertical-align:middle;margin-right:7px}
  .mini i{display:block;height:100%;background:var(--blue);border-radius:3px}
  .mini i.low{background:var(--red)} .mini i.good{background:var(--green)}
  .empty{padding:56px 20px;text-align:center;color:var(--ink3);font-size:13px;line-height:2}
  .empty b{color:var(--ink2);display:block;font-size:14px;margin-bottom:4px}
  /* drawer */
  .mask{position:fixed;inset:0;background:rgba(16,22,34,.36);opacity:0;pointer-events:none;
    transition:.2s;z-index:40}
  .mask.on{opacity:1;pointer-events:auto}
  .drawer{position:fixed;top:0;right:0;bottom:0;width:min(760px,94vw);background:#fff;
    transform:translateX(100%);transition:.26s cubic-bezier(.3,.8,.3,1);z-index:41;
    display:flex;flex-direction:column;box-shadow:-8px 0 32px rgba(16,22,34,.12)}
  .drawer.on{transform:none}
  .dw-h{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;
    align-items:flex-start;justify-content:space-between;gap:14px}
  .dw-h h2{font-size:17px;font-weight:600}
  .dw-h .sub2{font-size:12px;color:var(--ink3);margin-top:3px}
  .close{border:0;background:var(--bg);width:30px;height:30px;border-radius:6px;
    cursor:pointer;color:var(--ink2);font-size:16px;line-height:1;flex-shrink:0}
  .close:hover{background:var(--line);color:var(--ink)}
  .dw-sum{display:flex;gap:0;border-bottom:1px solid var(--line2);background:#fafbfd}
  .dw-sum div{flex:1;padding:12px 8px;text-align:center;border-right:1px solid var(--line2);min-width:0}
  .dw-sum div:last-child{border:0}
  .dw-sum .k{font-size:11px;color:var(--ink3)} .dw-sum .v{font-size:18px;font-weight:600;margin-top:1px;
    white-space:nowrap;font-variant-numeric:tabular-nums}
  .dw-body{overflow-y:auto;padding:8px 24px 40px;flex:1}
  .qitem{padding:16px 0;border-bottom:1px solid var(--line2);display:grid;
    grid-template-columns:30px 1fr;gap:12px}
  .qno{font-size:12px;font-weight:600;color:var(--ink3);padding-top:2px;font-variant-numeric:tabular-nums}
  .qstem{font-size:13.5px;font-weight:500;line-height:1.55;margin-bottom:8px}
  .opts{display:flex;flex-direction:column;gap:3px;margin-bottom:8px}
  .opt{font-size:12.5px;color:var(--ink2);padding:3px 9px;border-radius:4px;line-height:1.5}
  .opt.c{background:var(--green-l);color:var(--green);font-weight:500}
  .opt.w{background:var(--red-l);color:var(--red);text-decoration:line-through;
    text-decoration-color:rgba(192,57,43,.4)}
  .opt .m{font-weight:700;margin-right:5px}
  .verdict{font-size:11px;font-weight:600;padding:1px 7px;border-radius:4px;margin-left:8px;
    vertical-align:1px;white-space:nowrap;display:inline-block}
  .verdict.ok{background:var(--green-l);color:var(--green)}
  .verdict.no{background:var(--red-l);color:var(--red)}
  .exp{background:#fbfcfd;border-left:2px solid var(--gold);border-radius:0 5px 5px 0;
    padding:8px 12px;font-size:12.5px;color:var(--ink2);line-height:1.65}
  .exp b{color:var(--gold);font-weight:600;font-size:11px;letter-spacing:.4px;
    display:block;margin-bottom:2px}
  .warnbox{background:var(--gold-l);border:1px solid #eddfc0;color:#8a6a1f;
    padding:10px 14px;border-radius:6px;font-size:12px;margin:12px 0}
  @media(max-width:900px){
    .kpis{grid-template-columns:repeat(3,1fr)}
    .papers{grid-template-columns:1fr}
    .charts{grid-template-columns:1fr}
    .chart+.chart{border-left:0;border-top:1px solid var(--line2)}
    .hide-m{display:none}
    input[type=search]{width:100%}
    .bar{gap:8px}
  }
  @media(max-width:640px){
    .wrap{padding:0 14px}
    h1{font-size:18px}
    .kpis{grid-template-columns:repeat(2,1fr);gap:8px}
    .drawer{width:100vw}
    .dw-h,.dw-body{padding-left:16px;padding-right:16px}
    .dw-sum div{padding:10px 4px}
    .dw-sum .v{font-size:15px}
    #tableBox{overflow-x:auto;-webkit-overflow-scrolling:touch}
    td{padding:10px 9px}
    th{padding:9px 9px}
    .certbtn{padding:3px 7px;font-size:10px}
    th.lvcol{width:auto}
    .lven{display:none}
    td.num{white-space:nowrap}
  }

  /* ===== DTK_COMPAT：钉钉预览兼容样式 ===== */
  .dtk-toast{position:fixed;left:50%;bottom:34px;transform:translateX(-50%) translateY(8px);
    background:rgba(26,31,43,.95);color:#fff;font-size:13px;line-height:1.6;padding:10px 18px;
    border-radius:8px;z-index:9999;opacity:0;transition:.22s;pointer-events:none;max-width:82vw;
    box-shadow:0 10px 30px rgba(0,0,0,.28)}
  .dtk-toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
  .dtk-mask{position:fixed;inset:0;background:rgba(16,20,28,.82);z-index:9998;display:none;
    align-items:center;justify-content:center;padding:24px;flex-direction:column;gap:12px}
  .dtk-mask.on{display:flex}
  .dtk-mask img{max-width:min(96vw,1020px);max-height:calc(100vh - 150px);border-radius:6px;
    background:#fff;box-shadow:0 18px 50px rgba(0,0,0,.5)}
  .dtk-mask .cap{color:#fff;font-size:12.5px;opacity:.85;text-align:center;line-height:1.7}
  .dtk-mask .bar{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
  .dtk-mask .bar button{background:rgba(255,255,255,.13);color:#fff;border:1px solid rgba(255,255,255,.28);
    border-radius:6px;padding:7px 16px;font-size:13px;cursor:pointer}
  .dtk-mask .bar button:hover{background:rgba(255,255,255,.24)}
  .dtk-csv .box{background:#fff;border-radius:10px;width:min(780px,96vw);max-height:86vh;
    display:flex;flex-direction:column;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.35)}
  .dtk-csv .hd{padding:15px 20px 11px;font-size:15px;font-weight:600;border-bottom:1px solid var(--line2)}
  .dtk-csv .tip{padding:10px 20px 0;font-size:12.5px;color:var(--ink2);line-height:1.75}
  .dtk-csv textarea{flex:1;margin:12px 20px;min-height:190px;border:1px solid var(--line);border-radius:6px;
    padding:10px;font:12px/1.65 ui-monospace,Consolas,monospace;color:var(--ink);resize:none;outline:none;
    background:#fcfcfd}
  .dtk-csv .ft{padding:0 20px 16px;display:flex;gap:8px;justify-content:flex-end}
  .dtk-csv .ft button{border-radius:6px;padding:8px 16px;font-size:13px;cursor:pointer;
    border:1px solid var(--line);background:#fff;color:var(--ink2)}
  .dtk-csv .ft button.pri{background:var(--blue);color:#fff;border-color:var(--blue)}
  /* 导出结果面板 */
  .dtk-exp .box{background:#fff;border-radius:10px;width:min(1060px,97vw);max-height:88vh;
    display:flex;flex-direction:column;overflow:hidden}
  .dtk-exp .hd{padding:13px 18px 10px;font-size:15px;font-weight:600;display:flex;
    align-items:center;gap:10px;border-bottom:1px solid var(--line2)}
  .dtk-exp .hd .sub{font-size:12px;font-weight:400;color:var(--ink2)}
  .dtk-exp .hd .x{margin-left:auto;cursor:pointer;font-size:21px;line-height:1;
    color:#98A2B0;padding:0 2px 2px}
  .dtk-exp .hd .x:hover{color:var(--ink)}
  .dtk-exp .tabs{display:flex;gap:4px;padding:9px 18px 0;border-bottom:1px solid var(--line2)}
  .dtk-exp .tabs button{border:1px solid var(--line);border-bottom:none;background:#F7F9FC;
    border-radius:6px 6px 0 0;padding:6px 15px;font-size:12.5px;cursor:pointer;color:var(--ink2)}
  .dtk-exp .tabs button.on{background:#fff;border-color:var(--line);color:var(--ink);
    font-weight:600;position:relative;top:1px}
  .dtk-exp .body{flex:1;overflow:auto;padding:12px 18px 4px}
  .dtk-exp .pane{display:none}
  .dtk-exp .pane.on{display:block}
  .dtk-exp table.ec-t{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:fixed}
  .dtk-exp table.ec-t th{position:sticky;top:0;background:#F4F6FA;text-align:left;
    font-weight:600;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
  .dtk-exp table.ec-t td{padding:6px 8px;border-bottom:1px solid var(--line2);vertical-align:middle;
    white-space:nowrap}
  .dtk-exp table.ec-t th:last-child,.dtk-exp table.ec-t td:last-child{text-align:center}
  .dtk-exp table.ec-t td:nth-child(3){white-space:normal;word-break:break-word}
  .dtk-exp td.num{text-align:right;font-variant-numeric:tabular-nums}
  .dtk-exp td.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;color:var(--ink2)}
  .dtk-exp .ec-img{height:58px;border:1px solid var(--line);border-radius:4px;
    cursor:zoom-in;background:#fff;display:block}
  .dtk-exp .ec-na{color:#B6BDC8;font-size:11.5px}
  .dtk-exp .ec-lv{display:inline-block;min-width:26px;text-align:center;border-radius:4px;
    padding:1px 5px;font-size:11px;font-weight:600;background:#EEF2F8;color:#2B5EA8}
  .dtk-exp .ft{padding:10px 18px 14px;display:flex;gap:8px;align-items:center;
    border-top:1px solid var(--line2);flex-wrap:wrap}
  .dtk-exp .ft .hint{font-size:11.5px;color:var(--ink2);margin-right:auto;
    line-height:1.65;max-width:430px}
  .dtk-exp .ft button{border-radius:6px;padding:7px 14px;font-size:12.5px;cursor:pointer;
    border:1px solid var(--line);background:#fff;color:var(--ink)}
  .dtk-exp .ft button:hover{border-color:#B9C4D4}
  .dtk-exp .ft button.pri{background:var(--blue);color:#fff;border-color:var(--blue)}
  .dtk-exp textarea{width:100%;min-height:320px;border:1px solid var(--line);border-radius:6px;
    padding:10px 11px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;
    line-height:1.65;resize:vertical}
  @media (max-width:640px){
    .dtk-exp .box{width:96vw}
    .dtk-exp .ec-img{height:40px}
  }
</style>
</head>
<body>
<header>
  <div class="wrap h-top">
    <div>
      <h1><span class="dot"></span>环球商务英语级别测试 · 成绩查询</h1>
      <div class="meta" id="meta">加载中…</div>
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn" id="btnReload">重新载入</button>
      <button class="btn" id="btnPack" title="先筛选，再看结果；证书直接显示在表里，可打包下载">导出数据包</button>
      <button class="btn primary" id="btnCsv">导出 CSV</button>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="papers" id="papers"></div>
  <div class="kpis" id="kpis"></div>

  <div class="panel">
    <div class="bar">
      <div class="tabs" id="tabs"></div>
      <div class="spacer"></div>
      <input type="search" id="q" placeholder="搜索姓名 / 企业…">
      <select id="status">
        <option value="">全部结果</option>
        <option value="ex">优秀（≥80）</option>
        <option value="pa">通过（60–79）</option>
        <option value="fa">未通过（&lt;60）</option>
      </select>
      <select id="sortBy">
        <option value="submit_time">按提交时间</option>
        <option value="score">按得分</option>
        <option value="level">按级别</option>
      </select>
    </div>
    <div class="charts">
      <div class="chart">
        <div class="chart-t"><span>得分分布（按 10 分区间）</span><span id="histLg"></span></div>
        <div class="hist" id="hist"></div>
      </div>
      <div class="chart">
        <div class="chart-t"><span>各级别平均分</span></div>
        <div class="lvlist" id="lvlist"></div>
      </div>
    </div>
    <div id="tableBox"></div>
  </div>
</div>

<div class="mask" id="mask"></div>
<aside class="drawer" id="drawer">
  <div class="dw-h">
    <div><h2 id="dwName"></h2><div class="sub2" id="dwSub"></div></div>
    <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
      <span id="dwCert"></span>
      <button class="close" id="dwClose">×</button>
    </div>
  </div>
  <div class="dw-sum" id="dwSum"></div>
  <div class="dw-body" id="dwBody"></div>
</aside>

<script>
const DATA = /*__DATA__*/null;
const S = {level:'', q:'', status:'', sort:'submit_time', asc:false};

/* ---------- helpers ---------- */
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtTime = s => (s||'').replace('T',' ').slice(0,16);
const fmtDur = s => { s=+s||0; if(!s) return '—'; const m=Math.floor(s/60), ss=s%60;
  return m? (m+'分'+(ss?ss+'秒':'')) : (ss+'秒'); };
const fmtDurShort = s => { s=+s||0; if(!s) return '—'; const m=Math.floor(s/60), ss=s%60;
  return m? (m+'′'+(ss?String(ss).padStart(2,'0')+'″':'')) : (ss+'″'); };
const grade = r => r.score>=80 ? 'ex' : r.score>=60 ? 'pa' : 'fa';
const gradeText = g => ({ex:'优秀',pa:'通过',fa:'未通过'})[g]||'';

/* ---------- 级别身份 ---------- */
const LM = lv => DATA.levels[lv] || {};
const lvColor = lv => LM(lv).level_color || 'var(--blue)';
const lvCn = lv => LM(lv).level_cn || '';
const lvEn = lv => LM(lv).level_en || '';
const lvChip = (lv, sm) => `<span class="lvtag k-${esc(lv)}"
  style="background:${lvColor(lv)}${sm?';font-size:10px;padding:1px 6px':''}" title="${esc(lvEn(lv))}">${esc(lv)}</span>`;

function allRecords(){
  const out=[];
  Object.values(DATA.levels).forEach(L=>L.records.forEach(r=>out.push(r)));
  return out;
}
function currentRecords(){
  let rs = S.level ? DATA.levels[S.level].records.slice() : allRecords();
  if(S.status) rs = rs.filter(r=>grade(r)===S.status);
  if(S.q){ const k=S.q.toLowerCase();
    rs = rs.filter(r=>r.name.toLowerCase().includes(k)); }
  const dir = S.asc?1:-1;
  rs.sort((a,b)=>{
    if(S.sort==='score') return (a.score-b.score)*dir || a.submit_time.localeCompare(b.submit_time);
    if(S.sort==='level') return a.level.localeCompare(b.level)*dir || (a.score-b.score)*-1;
    return a.submit_time.localeCompare(b.submit_time)*dir;
  });
  return rs;
}

/* ---------- KPI ---------- */
function renderKpis(){
  const rs = allRecords();
  const n = rs.length;
  const avg = n? rs.reduce((s,r)=>s+r.score,0)/n : 0;
  const pass = rs.filter(r=>r.score>=60).length;
  const ex = rs.filter(r=>r.score>=80).length;
  const pct = v => n? Math.round(v/n*100) : 0;
  const cnt = lv => DATA.levels[lv] ? DATA.levels[lv].records.length : 0;
  const card = (k,v,cls,unit) => `<div class="kpi ${cls||''}">
      <div class="k">${k}</div><div class="v">${v}${unit?`<small>${unit}</small>`:''}</div></div>`;
  document.getElementById('kpis').innerHTML = [
    card('有效答卷', n, 'blue'),
    ...Object.keys(DATA.levels).map(lv =>
      `<div class="kpi lvk" style="box-shadow:inset 3px 0 0 ${lvColor(lv)}">
        <div class="k">${lvChip(lv, 1)}${esc(lvCn(lv))}</div>
        <div class="v" style="color:${lvColor(lv)}">${cnt(lv)}</div></div>`),
    card('平均分', n? avg.toFixed(1):'—', 'gold'),
    card('通过率 ≥60', n? pct(pass)+'%':'—', '', n?`(${pass}/${n})`:''),
  ].join('');
  document.getElementById('meta').innerHTML =
    `数据更新时间 ${esc(DATA.fetched_at)} · 共 ${n} 份有效答卷 · 优秀 ${ex} 份 ` +
    `（≥80）· 已生成证书 ${DATA.cert_count||0} 张 · 级别 ` +
    Object.keys(DATA.levels).map(lv =>
      `<span style="white-space:nowrap">${lvChip(lv, 1)}&nbsp;${esc(lvCn(lv))}</span>`).join('　') +
    ` · 点击任意一行查看逐题对错与解析`;
}

/* ---------- tabs ---------- */
function renderPapers(){
  const el = document.getElementById('papers');
  if(!el) return;
  el.innerHTML = Object.keys(DATA.levels).map(lv=>{
    const L = DATA.levels[lv];
    const scls = L.series_cls || 'biz';
    return `<div class="paper">
      <span class="lv" style="background:${lvColor(lv)}">${lv}<span class="e">${esc(lvCn(lv))}</span></span>
      <div class="info">
        <a class="u" href="${esc(L.url)}" target="_blank" rel="noopener">${esc(L.url.replace(/^https?:\/\//,''))}</a>
        <div class="c">${L.answer_count} 份答卷 · ${L.questions.length} 题 · 满分 ${L.total_score}</div>
        <div class="sn">${esc(L.series_name||'')} · ${esc(lvEn(lv))} · 证书${scls==='cls'?'蓝版':'红版'}</div>
      </div>
      <button data-copy="${esc(L.url)}">复制</button>
    </div>`;
  }).join('');
  el.querySelectorAll('button[data-copy]').forEach(b=>{
    b.onclick = async ()=>{
      const t = b.dataset.copy;
      try { await navigator.clipboard.writeText(t); }
      catch(e){ const ta=document.createElement('textarea'); ta.value=t;
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
      const old = b.textContent; b.textContent='已复制'; setTimeout(()=>b.textContent=old,1200);
    };
  });
}

function renderTabs(){
  const items = [['', '全部', allRecords().length, '']];
  Object.keys(DATA.levels).forEach(lv=>items.push([lv, lv, DATA.levels[lv].records.length, lvColor(lv)]));
  document.getElementById('tabs').innerHTML = items.map(([v,label,c,col])=>
    `<button class="tab ${S.level===v?'on':''}" data-lv="${v}" title="${esc(lvCn(v)||'')}">` +
    `${col?`<i class="kdot" style="background:${col}"></i>`:''}${label}<u>${c}</u></button>`).join('');
  document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{S.level=b.dataset.lv; renderAll();});
}

/* ---------- charts ---------- */
function renderCharts(){
  const rs = S.level ? DATA.levels[S.level].records : allRecords();
  const lvs = Object.keys(DATA.levels);
  const bins = Array.from({length:10},()=>({}));
  rs.forEach(r=>{ const i=Math.min(9,Math.max(0,Math.floor(r.score/10)));
    bins[i][r.level] = (bins[i][r.level]||0) + 1; });
  const totals = bins.map(b=>lvs.reduce((s,lv)=>s+(b[lv]||0),0));
  const mx = Math.max(1,...totals);
  document.getElementById('hist').innerHTML = bins.map((b,i)=>{
    const tot = totals[i];
    const H = tot ? Math.round(tot/mx*88) : 2;
    const segs = tot ? lvs.filter(lv=>b[lv]).map(lv=>{
      const px = Math.max(2, Math.round(H*b[lv]/tot));
      return `<i style="height:${px}px;background:${lvColor(lv)}"
        title="${esc(lv)} ${esc(lvCn(lv))}：${b[lv]} 人"></i>`;
    }).join('') : `<i style="height:2px;background:#e6e9ef"></i>`;
    return `<div class="hbar"><div class="n">${tot||''}</div>
      <div class="bwrap">${segs}</div>
      <div class="l">${i*10}</div></div>`;
  }).join('');

  const lg = document.getElementById('histLg');
  if(lg) lg.innerHTML = (S.level ? [S.level] : lvs)
    .map(lv=>`<span class="lg"><i style="background:${lvColor(lv)}"></i>${esc(lv)} ${esc(lvCn(lv))}</span>`).join('');

  const rows = lvs.map(lv=>{
    const list = DATA.levels[lv].records;
    const a = list.length? list.reduce((s,r)=>s+r.score,0)/list.length : null;
    const w = a==null? 0 : Math.round(a);
    const col = lvColor(lv);
    return `<div class="lvrow"><span class="lb" title="${esc(lvEn(lv))}">
        <i class="kdot" style="background:${col}"></i>${esc(lv)}</span>
      <span class="track"><span class="fill ${a==null?'na':''}"
        style="width:${w}%;${a==null?'':'background:'+col}"></span></span>
      <span class="vv">${a==null?'暂无':a.toFixed(1)}</span></div>`;
  });
  rows.push(`<div class="lvrow" style="border-top:1px dashed var(--line);padding-top:10px">
      <span class="lb" style="color:var(--ink3)">全部</span>
      <span class="track"><span class="fill" style="width:${rs.length?Math.round(rs.reduce((s,r)=>s+r.score,0)/rs.length):0}%;background:var(--gold)"></span></span>
      <span class="vv">${rs.length?(rs.reduce((s,r)=>s+r.score,0)/rs.length).toFixed(1):'暂无'}</span></div>`);
  document.getElementById('lvlist').innerHTML = rows.join('');
}

/* ---------- table ---------- */
function renderTable(){
  const rs = currentRecords();
  const box = document.getElementById('tableBox');
  if(!rs.length){
    const total = allRecords().length;
    box.innerHTML = `<div class="empty">
      ${total? '<b>当前筛选条件下没有答卷</b>换个条件试试' :
        '<b>还没有收到有效答卷</b>学员交卷后，点右上角「重新载入」即可看到成绩'}
    </div>`;
    return;
  }
  const head = `<tr>
    <th style="width:44px">#</th>
    <th data-s="level" class="lvcol">级别</th>
    <th>考生 / 企业</th>
    <th class="num" data-s="score">得分</th>
    <th class="num hide-m">正确题数</th>
    <th class="hide-m">正确率</th>
    <th class="num hide-m">用时</th>
    <th>结果</th>
    <th>证书</th>
    <th class="hide-m" data-s="submit_time">提交时间</th>
  </tr>`;
  const body = rs.map((r,i)=>{
    const g = grade(r), rate = r.count? Math.round(r.right/r.count*100):0;
    const cls = rate>=60?'good':rate>=40?'':'low';
    const scls = (DATA.levels[r.level]||{}).series_cls || 'biz';
    return `<tr data-jid="${esc(r.jid)}" data-lv="${esc(r.level)}">
      <td style="color:var(--ink3)" class="num">${i+1}</td>
      <td><span class="lvtag" style="background:${lvColor(r.level)}"
             title="${esc(lvEn(r.level))}">${esc(r.level)}</span><span class="lven">${esc(lvCn(r.level))}</span></td>
      <td><div class="nm">${esc(r.name)}</div>${r.province?`<div class="sub">${esc(r.province)}</div>`:''}</td>
      <td class="num"><span class="sc" style="color:${g==='fa'?'var(--red)':g==='ex'?'var(--gold)':'var(--ink)'}">${r.score%1?r.score.toFixed(1):r.score}</span><span style="color:var(--ink3);font-size:11px"> /${r.total}</span></td>
      <td class="num hide-m">${r.right}<span style="color:var(--ink3)">/${r.count}</span></td>
      <td class="hide-m"><span class="mini"><i class="${cls}" style="width:${rate}%"></i></span><span style="font-size:12px;color:var(--ink2)">${rate}%</span></td>
      <td class="num hide-m" style="color:var(--ink2)">${fmtDur(r.seconds)}</td>
      <td><span class="tag ${g}">${gradeText(g)}</span></td>
      <td>${r.cert
        ? `<a class="certbtn ${scls}" href="证书/${encodeURIComponent(r.cert.file)}" target="_blank"
             onclick="event.stopPropagation()" title="证书编号 ${esc(r.cert.no)}">查看证书</a>`
        : `<span style="color:var(--ink3);font-size:12px">—</span>`}</td>
      <td class="hide-m" style="color:var(--ink3);font-size:12px">${fmtTime(r.submit_time)}</td>
    </tr>`;
  }).join('');
  box.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  document.querySelectorAll('th[data-s]').forEach(th=>{
    if(th.dataset.s===S.sort){ th.classList.add('sorted'); if(S.asc) th.classList.add('asc'); }
    th.onclick=()=>{
      if(S.sort===th.dataset.s) S.asc=!S.asc; else {S.sort=th.dataset.s; S.asc=false;}
      renderTable();
    };
  });
  box.querySelectorAll('tbody tr').forEach(tr=>{
    tr.onclick=()=>openDrawer(tr.dataset.lv, tr.dataset.jid);
  });
}

/* ---------- drawer ---------- */
function findRecord(lv,jid){
  return (DATA.levels[lv]?.records||[]).find(r=>r.jid===jid);
}
function openDrawer(lv,jid){
  const r = findRecord(lv,jid); if(!r) return;
  const g = grade(r), rate = r.count? Math.round(r.right/r.count*100):0;
  document.getElementById('dwName').textContent = r.name;
  const sname = (DATA.levels[lv]||{}).series_name || '';
  document.getElementById('dwSub').innerHTML =
    `${lvChip(lv)}<span class="lven" style="margin-left:6px">${esc(lvCn(lv))}</span>` +
    `<span style="margin-left:10px">${sname? esc(sname)+' · ':''}${r.count} 题 · 提交于 ${fmtTime(r.submit_time)}` +
    `${r.province? ' · '+esc(r.province):''}</span>`;
  document.getElementById('dwCert').innerHTML = r.cert
    ? `<a class="certbtn ${(DATA.levels[lv]||{}).series_cls||'biz'}" href="证书/${encodeURIComponent(r.cert.file)}" target="_blank">查看证书</a>
       <a class="certbtn ${(DATA.levels[lv]||{}).series_cls||'biz'}" style="margin-left:6px"
          href="证书/${encodeURIComponent(r.cert.pdf||'')}" target="_blank">打印版 PDF</a>`
    : '';
  document.getElementById('dwSum').innerHTML = `
    <div><div class="k">得分</div><div class="v" style="color:${g==='fa'?'var(--red)':g==='ex'?'var(--gold)':'var(--green)'}">${r.score%1?r.score.toFixed(1):r.score}</div></div>
    <div><div class="k">答对</div><div class="v">${r.right}/${r.count}</div></div>
    <div><div class="k">正确率</div><div class="v">${rate}%</div></div>
    <div><div class="k">用时</div><div class="v" style="font-size:15px;padding-top:3px">${fmtDurShort(r.seconds)}</div></div>
    <div><div class="k">结果</div><div class="v" style="font-size:14px;padding-top:4px"><span class="tag ${g}">${gradeText(g)}</span></div></div>`;

  let warn = '';
  if(r.missing>0) warn = `<div class="warnbox">该答卷有 ${r.missing} 题未出现在提交数据中（可能中途退出或跳题），对错统计仅含已答的 ${r.count} 题。</div>`;
  if(Math.abs(r.calc_score-r.score)>0.01 && r.missing===0 && DATA.levels[lv])
    warn += `<div class="warnbox">按逐题计分累加为 ${r.calc_score} 分，问卷星记录 ${r.score} 分，差异可能来自人工调分或题目分值变更。</div>`;

  const qs = r.details.map(d=>{
    const ch = new Set(d.chosen), co = new Set(d.correct);
    const opts = d.options.map(o=>{
      const isC=co.has(o.letter), isW=ch.has(o.letter)&&!isC;
      let mark='';
      if(isC) mark = `<span style="font-size:10px">✓ ${ch.has(o.letter)?'你选对了':'正确答案'}</span>`;
      else if(isW) mark = `<span style="font-size:10px">✗ 你的选择</span>`;
      return `<div class="opt ${isC?'c':''} ${isW?'w':''}">
        <span class="m">${esc(o.letter)}</span>${esc(o.text)}${mark?' '+mark:''}</div>`;
    }).join('');
    const chosenTxt = d.chosen.length? d.chosen.join('') : '未答';
    return `<div class="qitem">
      <div class="qno">${d.no}</div>
      <div>
        <div class="qstem">${esc(d.stem)}
          <span class="verdict ${d.ok?'ok':'no'}">${d.ok?'答对 '+d.score+'分':'答错 · 你选 '+esc(chosenTxt)}</span></div>
        <div class="opts">${opts}</div>
        ${d.explanation? `<div class="exp"><b>解 析</b>${esc(d.explanation)}</div>`:''}
      </div>
    </div>`;
  }).join('');

  document.getElementById('dwBody').innerHTML = warn + qs;
  document.getElementById('dwBody').scrollTop = 0;
  document.getElementById('drawer').classList.add('on');
  document.getElementById('mask').classList.add('on');
  document.body.style.overflow = 'hidden';
}
function closeDrawer(){
  document.getElementById('drawer').classList.remove('on');
  document.getElementById('mask').classList.remove('on');
  document.body.style.overflow = '';
}

/* ---------- csv ---------- */
function buildCsv(rs){
  const head = ['序号','级别','级别名称','姓名/企业','得分','总分','答对题数','总题数','正确率','用时(秒)','结果','证书编号','提交时间','地区','证书文件'];
  const lines = [head.join(',')];
  rs.forEach((r,i)=>{
    const row = [i+1, r.level, lvCn(r.level), r.name, r.score, r.total, r.right, r.count,
      (r.count? Math.round(r.right/r.count*100):0)+'%', r.seconds, gradeText(grade(r)),
      r.cert? r.cert.no : '', r.submit_time, r.province,
      r.cert ? ('证书/' + String(r.cert.file || r.cert.slug || '').replace(/\.[^.]+$/, '') + '.png') : ''];
    lines.push(row.map(v=>{
      const s = String(v==null?'':v);
      return /[",\n]/.test(s) ? '"'+s.replace(/"/g,'""')+'"' : s;
    }).join(','));
  });
  return lines.join('\r\n');
}

function csvName(){
  const d = new Date(), p = n=>String(n).padStart(2,'0');
  return `成绩导出_${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.csv`;
}

/* ---------- 导出：结果面板（数据表含证书 / CSV 文本） ---------- */
function eh(s){
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function certStemOf(r){
  if(!r || !r.cert) return '';
  return String(r.cert.file || r.cert.slug || '').replace(/\.[^.]+$/, '');
}
function certRecOf(stem){
  if(!stem || !window.CERT_B64) return null;
  if(window.CERT_B64[stem]) return window.CERT_B64[stem];
  var low = stem.toLowerCase();
  for(var k in window.CERT_B64) if(k.toLowerCase() === low) return window.CERT_B64[k];
  return null;
}
function certImgOf(stem){
  var rec = certRecOf(stem);
  if(!rec) return '';
  if(typeof rec === 'string') return rec;
  return rec.png || rec.jpg || rec.jpeg || rec.webp || '';
}
function filterLabel(){
  var t = [S.level ? ('级别 ' + S.level) : '全部级别'];
  if(S.status === 'ex') t.push('优秀');
  else if(S.status === 'pa') t.push('通过');
  else if(S.status === 'fa') t.push('未通过');
  if(S.q) t.push('搜索「' + S.q + '」');
  return t.join(' · ');
}
function pctOf(r){ return (r.count ? Math.round(r.right / r.count * 100) : 0) + '%'; }

function exportTableHtml(rs, withImg){
  var rows = rs.map(function(r, i){
    var stem = certStemOf(r);
    var srcImg = withImg ? certImgOf(stem) : '';
    var cell;
    if(srcImg){
      cell = '<img class="ec-img" src="' + srcImg + '" data-file="' + eh(stem + '.png') + '" alt="证书">';
    } else if(stem){
      cell = '<span class="ec-na">图片未内嵌</span>';
    } else {
      cell = '<span class="ec-na">未出证</span>';
    }
    return '<tr>'
      + '<td class="num">' + (i + 1) + '</td>'
      + '<td><span class="ec-lv">' + eh(r.level) + '</span></td>'
      + '<td>' + eh(r.name) + '</td>'
      + '<td class="num">' + r.score + '</td>'
      + '<td class="num">' + r.right + '/' + r.count + '</td>'
      + '<td class="num">' + pctOf(r) + '</td>'
      + '<td><span class="tag ' + grade(r) + '">' + gradeText(grade(r)) + '</span></td>'
      + '<td class="mono">' + eh(r.cert ? r.cert.no : '—') + '</td>'
      + '<td>' + cell + '</td>'
      + '</tr>';
  }).join('');
  return '<table class="ec-t"><colgroup>'
    + '<col style="width:42px"><col style="width:56px"><col>'
    + '<col style="width:56px"><col style="width:64px"><col style="width:66px">'
    + '<col style="width:74px"><col style="width:172px"><col style="width:84px">'
    + '</colgroup><thead><tr>'
    + '<th>#</th><th>级别</th><th>姓名 / 企业</th><th>得分</th><th>对/总</th>'
    + '<th>正确率</th><th>结果</th><th>证书编号</th><th>证书</th>'
    + '</tr></thead><tbody>' + rows + '</tbody></table>';
}

/* 复制到 Excel 用 TSV，比 CSV 粘贴更稳（不会因为逗号错列） */
function buildTsv(rs){
  var head = ['序号','级别','姓名/企业','得分','答对','总题','正确率','结果','证书编号','证书文件'];
  var lines = [head.join('\t')];
  rs.forEach(function(r, i){
    var stem = certStemOf(r);
    lines.push([i + 1, r.level, r.name, r.score, r.right, r.count, pctOf(r),
      gradeText(grade(r)), r.cert ? r.cert.no : '', stem ? ('证书/' + stem + '.png') : ''
    ].join('\t'));
  });
  return lines.join('\n');
}

function showExportPanel(rs, tab){
  var el = document.getElementById('dtkExp');
  if(!el){
    el = document.createElement('div');
    el.id = 'dtkExp'; el.className = 'dtk-mask dtk-exp';
    el.innerHTML = '<div class="box">'
      + '<div class="hd">导出结果<span class="sub" id="dtkExpSub"></span>'
      + '<span class="x" id="dtkExpX">×</span></div>'
      + '<div class="tabs">'
      + '<button data-tab="tbl" id="dtkExpTab1">数据表 · 含证书</button>'
      + '<button data-tab="csv" id="dtkExpTab2">CSV 文本</button>'
      + '</div>'
      + '<div class="body">'
      + '<div class="pane" id="dtkExpPane1"></div>'
      + '<div class="pane" id="dtkExpPane2"><textarea id="dtkExpCsv" spellcheck="false"></textarea></div>'
      + '</div>'
      + '<div class="ft"><span class="hint" id="dtkExpHint"></span>'
      + '<button id="dtkExpCopyT">复制表格</button>'
      + '<button id="dtkExpCopyC">复制 CSV</button>'
      + '<button id="dtkExpDl" class="pri">下载数据包</button>'
      + '<button id="dtkExpDlC">下载 CSV</button>'
      + '<button id="dtkExpClose">关闭</button>'
      + '</div></div>';
    document.body.appendChild(el);

    el.addEventListener('click', function(e){
      if(e.target === el){ el.classList.remove('on'); return; }
      var img = e.target.closest && e.target.closest('img.ec-img');
      if(img){
        showCertLightbox(img.getAttribute('data-file'));
      }
    });
    document.getElementById('dtkExpX').onclick = function(){ el.classList.remove('on'); };
    document.getElementById('dtkExpClose').onclick = function(){ el.classList.remove('on'); };
    document.getElementById('dtkExpTab1').onclick = function(){ switchTab('tbl'); };
    document.getElementById('dtkExpTab2').onclick = function(){ switchTab('csv'); };

    document.getElementById('dtkExpCopyT').onclick = async function(){
      var ok = await dtkCopy(buildTsv(currentRecords()));
      if(ok) dtkToast('表格已复制。Excel 里选中 A1 → Ctrl+V');
      else dtkToast('复制被拦了。可切到「CSV 文本」手动全选复制', 3600);
    };
    document.getElementById('dtkExpCopyC').onclick = async function(){
      var ta = document.getElementById('dtkExpCsv');
      ta.focus(); ta.select();
      var ok = await dtkCopy(ta.value);
      if(ok) dtkToast('CSV 已复制。Excel 里选中 A1 → Ctrl+V');
      else dtkToast('复制被拦了：文本框已全选，请按 Ctrl+C', 3600);
    };
    document.getElementById('dtkExpDl').onclick = function(){
      downloadPack(currentRecords());
    };
    document.getElementById('dtkExpDlC').onclick = function(){
      downloadCsv(currentRecords());
    };
  }

  function switchTab(t){
    document.getElementById('dtkExpTab1').classList.toggle('on', t === 'tbl');
    document.getElementById('dtkExpTab2').classList.toggle('on', t === 'csv');
    document.getElementById('dtkExpPane1').classList.toggle('on', t === 'tbl');
    document.getElementById('dtkExpPane2').classList.toggle('on', t === 'csv');
  }

  var withCert = rs.filter(function(r){ return !!certImgOf(certStemOf(r)); }).length;
  document.getElementById('dtkExpSub').textContent =
    '　' + filterLabel() + ' · 命中 ' + rs.length + ' 条 · 含证书 ' + withCert + ' 份';
  document.getElementById('dtkExpPane1').innerHTML = exportTableHtml(rs, true);
  document.getElementById('dtkExpCsv').value = buildCsv(rs);

  var canDl = !DTK_FRAME;
  document.getElementById('dtkExpDl').style.display = canDl ? '' : 'none';
  document.getElementById('dtkExpDlC').style.display = canDl ? '' : 'none';
  document.getElementById('dtkExpHint').innerHTML = canDl
    ? '「下载数据包」= 成绩明细.csv + 证书原图 + 带证书图的 HTML 表，打成一个 zip。'
    : '钉钉预览禁止下载文件：这里可以直接看筛选后的数据与证书，复制按钮可用。'
      + '要打包成文件，在电脑上双击「成绩查询_单文件版.html」再点同一按钮。';

  switchTab(tab || 'tbl');
  el.classList.add('on');
}

function openExport(tab){
  var rs = currentRecords();
  if(!rs.length){ dtkToast('当前筛选下没有可导出的答卷'); return; }
  showExportPanel(rs, tab);
}

function downloadCsv(rs){
  var csv = buildCsv(rs);
  try{
    var blob = new Blob(['\ufeff' + csv], {type: 'text/csv;charset=utf-8'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '成绩导出_' + packTag(rs) + '.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1500);
    dtkToast('已开始下载 ' + rs.length + ' 条成绩');
  }catch(e){
    dtkToast('下载被拦：' + e.message, 4000);
  }
}

function exportCsv(){ openExport('csv'); }

/* ---------- init ---------- */
function renderAll(){ renderPapers(); renderKpis(); renderTabs(); renderCharts(); renderTable(); }

document.getElementById('q').oninput = e => { S.q = e.target.value.trim(); renderTable(); };
document.getElementById('status').onchange = e => { S.status = e.target.value; renderTable(); };
document.getElementById('sortBy').onchange = e => { S.sort = e.target.value; S.asc=false; renderTable(); };

/* ===== 按筛选导出数据包（CSV + 证书 PNG/PDF → ZIP，无外部依赖） ===== */
var CRC_T = (function(){
  var t = [], c, n, k;
  for(n = 0; n < 256; n++){
    c = n;
    for(k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(u8){
  var c = 0xFFFFFFFF;
  for(var i = 0; i < u8.length; i++) c = CRC_T[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}
function u8Of(s){ return new TextEncoder().encode(s); }
function b64ToBytes(b64){
  var pure = String(b64).indexOf(',') >= 0 ? String(b64).split(',')[1] : String(b64);
  var bin = atob(pure);
  var a = new Uint8Array(bin.length);
  for(var i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return a;
}
function dosStamp(){
  var d = new Date();
  var date = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  var time = (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2);
  return {date: date, time: time};
}
function zipStore(files){
  var st = dosStamp(), parts = [], central = [], offset = 0;
  files.forEach(function(f){
    var name = u8Of(f.name), data = f.data, crc = crc32(data);
    var lh = new Uint8Array(30 + name.length), dv = new DataView(lh.buffer);
    dv.setUint32(0, 0x04034b50, true);      // local file header
    dv.setUint16(4, 20, true);              // version needed
    dv.setUint16(6, 0x0800, true);          // UTF-8 文件名
    dv.setUint16(8, 0, true);               // method = store
    dv.setUint16(10, st.time, true);
    dv.setUint16(12, st.date, true);
    dv.setUint32(14, crc, true);
    dv.setUint32(18, data.length, true);
    dv.setUint32(22, data.length, true);
    dv.setUint16(26, name.length, true);
    dv.setUint16(28, 0, true);
    lh.set(name, 30);
    parts.push(lh, data);

    var ch = new Uint8Array(46 + name.length), cv = new DataView(ch.buffer);
    cv.setUint32(0, 0x02014b50, true);      // central directory
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, st.time, true);
    cv.setUint16(14, st.date, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, data.length, true);
    cv.setUint32(24, data.length, true);
    cv.setUint16(28, name.length, true);
    cv.setUint32(42, offset, true);
    ch.set(name, 46);
    central.push(ch);
    offset += lh.length + data.length;
  });
  var cdSize = central.reduce(function(s, c){ return s + c.length; }, 0);
  var eocd = new Uint8Array(22), ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, offset, true);
  var out = new Uint8Array(offset + cdSize + 22), p = 0;
  parts.forEach(function(c){ out.set(c, p); p += c.length; });
  central.forEach(function(c){ out.set(c, p); p += c.length; });
  out.set(eocd, p);
  return out;
}

function packTag(rs){
  var tag = [];
  if(S.level) tag.push(S.level);
  if(S.status === 'ex') tag.push('优秀');
  else if(S.status === 'pa') tag.push('通过');
  else if(S.status === 'fa') tag.push('未通过');
  if(S.q) tag.push(String(S.q).replace(/[\\/:*?"<>|\s]+/g, ''));
  tag.push(rs.length + '条');
  var d = new Date(), p = function(n){ return String(n).padStart(2, '0'); };
  return tag.join('_') + '_' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate());
}

/* 返回 [{name, data}]，供导出与测试共用 */
function buildReportHtml(rs){
  var css = 'body{margin:0;padding:26px 30px;font:13px/1.6 -apple-system,BlinkMacSystemFont,'
    + '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#1B2430;background:#fff}'
    + 'h1{font-size:19px;margin:0 0 4px}p.meta{color:#66707E;font-size:12.5px;margin:0 0 16px}'
    + 'table{border-collapse:collapse;width:100%;font-size:12.5px}'
    + 'th{background:#F4F6FA;text-align:left;font-weight:600;padding:7px 8px;border-bottom:1px solid #E4E8EF}'
    + 'td{padding:6px 8px;border-bottom:1px solid #EEF1F5;vertical-align:middle}'
    + 'td.num{text-align:right}.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;color:#4A5462}'
    + 'img{height:70px;border:1px solid #E4E8EF;border-radius:4px;display:block}'
    + '.ec-lv{display:inline-block;min-width:26px;text-align:center;border-radius:4px;'
    + 'padding:1px 5px;font-size:11px;font-weight:600;background:#EEF2F8;color:#2B5EA8}'
    + '.na{color:#B6BDC8;font-size:11.5px}'
    + '@media print{body{padding:10px}h1{font-size:16px}}';
  return '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
    + '<title>成绩明细 · ' + eh(filterLabel()) + '</title><style>' + css + '</style></head><body>'
    + '<h1>环球商务英语级别测试 · 成绩明细</h1>'
    + '<p class="meta">筛选条件：' + eh(filterLabel()) + '　·　共 ' + rs.length + ' 条'
    + '　·　导出于 ' + new Date().toLocaleString('zh-CN') + '　·　证书已内嵌，双击本文件即可查看</p>'
    + exportTableHtml(rs, true)
    + '</bo' + 'dy></ht' + 'ml>';
}

function buildPackFiles(rs){
  var files = [
    {name: '成绩明细.csv', data: u8Of('\ufeff' + buildCsv(rs))},
    {name: '成绩明细（含证书）.html', data: u8Of(buildReportHtml(rs))}
  ];
  var got = 0, lack = 0;
  rs.forEach(function(r){
    if(!r.cert) return;
    var stem = String(r.cert.file || r.cert.slug || '').replace(/\.[^.]+$/, '');
    var key = null, rec = null;
    if(window.CERT_B64){
      for(var k in window.CERT_B64){
        if(k.toLowerCase() === stem.toLowerCase()){ key = k; rec = window.CERT_B64[k]; break; }
      }
    }
    if(!rec){ lack++; return; }
    if(typeof rec === 'string'){
      files.push({name: '证书/' + stem + '.png', data: b64ToBytes(rec)}); got++;
    } else {
      ['png', 'jpg', 'jpeg', 'webp', 'pdf'].forEach(function(ext){
        if(rec[ext]){ files.push({name: '证书/' + stem + '.' + ext, data: b64ToBytes(rec[ext])}); got++; }
      });
    }
  });
  return {files: files, certCount: got, lack: lack};
}

function exportPack(){ openExport('tbl'); }

function downloadPack(rs){
  if(!rs.length){ dtkToast('当前筛选下没有可导出的答卷'); return; }
  if(!window.CERT_B64){
    dtkToast('这份页面没内嵌证书，只能导出 CSV。请打开「成绩查询_单文件版.html」再打包。', 4600);
    downloadCsv(rs);
    return;
  }
  var built = buildPackFiles(rs);
  try{
    var bytes = zipStore(built.files);
    var blob = new Blob([bytes], {type: 'application/zip'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '成绩数据包_' + packTag(rs) + '.zip';
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 2500);
    dtkToast('已打包：' + rs.length + ' 条成绩 + ' + built.certCount + ' 个证书文件'
             + (built.lack ? ('，' + built.lack + ' 份缺证书') : '') + '（含带证书的 HTML 表）', 3800);
  }catch(err){
    dtkToast('打包失败：' + err.message, 4000);
  }
}

document.getElementById('btnCsv').onclick = exportCsv;
document.getElementById('btnPack').onclick = exportPack;
document.getElementById('btnReload').onclick = ()=>{
  if(!DTK_TOP){
    dtkToast('当前是生成时的数据快照，页面本身不能拉数据。有新答卷时由上架同事重新同步，链接不变。', 4200);
  } else {
    alert('数据为生成时的快照。\n\n要刷新成绩：双击同目录下的「刷新数据.bat」，\n重新生成后按 Ctrl+R 刷新本页即可。');
  }
};
document.getElementById('dwClose').onclick = closeDrawer;
document.getElementById('mask').onclick = closeDrawer;
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeDrawer(); });

if(!DATA || !DATA.levels){
  document.getElementById('meta').textContent = '数据未载入';
  document.getElementById('tableBox').innerHTML = '<div class="empty"><b>页面数据缺失</b>请先运行 update.py 生成</div>';
} else { renderAll(); }
</script>

<script>
/* ===== DTK_COMPAT：受限预览环境兜底层 =====
   拦掉所有会被静默失败的动作，换成页面内一定能看到的反馈

   注意（2026-11-16 修正）：原来用「在 iframe 里 = 钉钉」判断，把这个页面
   挂到 WorkBuddy 资料库（workbuddy.link）后也被误判成钉钉预览，导致
   「下载数据包」按钮被隐藏、a[download] 被拦 —— 但资料库那层 iframe 的
   sandbox 明确带 allow-downloads，下载其实是通的。
   现在只认「钉钉」：顶层窗口不算；在 iframe 里时看 top 域名 / referrer /
   UA 是否含 dingtalk、alidocs。 */
var DTK_TOP = (function(){ try { return window.self === window.top; } catch(e){ return false; } })();
var DTK_FRAME = (function(){
  if(DTK_TOP) return false;
  var probe = "";
  try { probe += (window.top.location.hostname || "") + " "; } catch(e){}
  try { probe += (document.referrer || "") + " "; } catch(e){}
  probe += (navigator.userAgent || "");
  return /dingtalk|alidocs/i.test(probe);
})();

function dtkToast(msg, ms){
  var el = document.getElementById('dtkToast');
  if(!el){
    el = document.createElement('div');
    el.id = 'dtkToast'; el.className = 'dtk-toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('on');
  clearTimeout(el._t);
  el._t = setTimeout(function(){ el.classList.remove('on'); }, ms || 2400);
}

async function dtkCopy(text){
  try{
    if(navigator.clipboard && navigator.clipboard.writeText){
      /* 沙箱里 writeText 可能既不 resolve 也不 reject，必须自带超时 */
      var ok = await Promise.race([
        navigator.clipboard.writeText(text).then(function(){ return true; }).catch(function(){ return false; }),
        new Promise(function(res){ setTimeout(function(){ res(false); }, 500); })
      ]);
      if(ok) return true;
    }
  }catch(e){}
  try{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    var ok = document.execCommand('copy');
    ta.remove();
    return ok;
  }catch(e){ return false; }
}

/* 证书：本地用相对路径；上架版由 pack_html.py 注入 CERT_B64 走 data URI */
function certURL(f){
  if(window.CERT_B64 && window.CERT_B64[f]) return window.CERT_B64[f];
  return '证书/' + encodeURIComponent(f);
}
function dataToBlobURL(u){
  var parts = u.split(',');
  var mime = (parts[0].match(/:(.*?);/) || [null,'application/octet-stream'])[1];
  var bin = atob(parts[1]);
  var arr = new Uint8Array(bin.length);
  for(var i=0;i<bin.length;i++) arr[i] = bin.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], {type: mime}));
}

function showCertLightbox(file){
  var src = certURL(file);
  var el = document.getElementById('dtkLb');
  if(!el){
    el = document.createElement('div');
    el.id = 'dtkLb'; el.className = 'dtk-mask';
    el.innerHTML = '<img id="dtkLbImg" alt="证书">' +
      '<div class="cap" id="dtkLbCap"></div>' +
      '<div class="bar"><button id="dtkLbOpen">在新标签打开原图</button>' +
      '<button id="dtkLbClose">关闭</button></div>';
    document.body.appendChild(el);
    el.addEventListener('click', function(e){ if(e.target === el) el.classList.remove('on'); });
    document.getElementById('dtkLbClose').onclick = function(){ el.classList.remove('on'); };
    document.getElementById('dtkLbOpen').onclick = function(){
      var u = document.getElementById('dtkLbImg').getAttribute('src');
      var blob = /^data:/i.test(u) ? dataToBlobURL(u) : u;
      var w = null;
      try { w = window.open(blob, '_blank'); } catch(e){}
      if(!w) dtkToast('预览环境禁止新窗口。右键/长按图片可直接保存。', 3600);
    };
  }
  document.getElementById('dtkLbImg').src = src;
  document.getElementById('dtkLbCap').textContent =
    file.replace(/\.(png|jpg|jpeg|webp)$/i,'') + ' · 右键或长按图片可另存为';
  el.classList.add('on');
}

function openPdf(file){
  var src = certURL(file);
  var url = /^data:/i.test(src) ? dataToBlobURL(src) : src;
  var w = null;
  try { w = window.open(url, '_blank'); } catch(e){}
  if(!w) dtkToast('预览环境禁止新窗口。打印版 PDF 请在钉钉外打开本页，或找市场同事要原件。', 4200);
}

/* 拦截证书点击：统一走页内灯箱，不依赖新窗口/相对路径
   钉钉/资料库会把 href 重写成 https://…/证书/x.png，所以按末尾「证书/」取文件名 */
function certNameFromHref(href){
  if(!href) return '';
  try { href = decodeURIComponent(href); } catch(e){}
  var i = href.lastIndexOf('证书/');
  if(i < 0) return '';
  return href.slice(i + 3).split(/[?#]/)[0].replace(/^\/+/, '');
}
document.addEventListener('click', function(e){
  var a = e.target.closest && e.target.closest('a');
  if(!a) return;
  var f = certNameFromHref(a.getAttribute('href'));
  if(!f) return;
  // 单文件版由 pack_html.py 注入的 #certLb 弹层接管（功能更全：缩放 / 下载 / PDF）
  if(document.getElementById('certLb')) return;
  e.preventDefault();
  e.stopPropagation();
  if(/\.pdf$/i.test(f)) openPdf(f);
  else showCertLightbox(f);
}, true);

/* 任何 download 链接在沙箱里点了都没反应 —— 统一给明确提示，别让人以为是坏了 */
document.addEventListener('click', function(e){
  if(!DTK_FRAME) return;
  var a = e.target.closest && e.target.closest('a[download]');
  if(!a) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  dtkToast('预览环境不支持下载文件。要原件请在浏览器里打开本页，或找上架同事要。', 4400);
}, true);

/* 链接复制兜底面板：沙箱里 clipboard / execCommand 都可能被拦，给可手动选中的文本框 */
function showLinkPanel(url, tip){
  var el = document.getElementById('dtkLink');
  if(!el){
    el = document.createElement('div');
    el.id = 'dtkLink'; el.className = 'dtk-mask dtk-csv';
    el.innerHTML = '<div class="box">' +
      '<div class="hd">复制链接</div>' +
      '<div class="tip" id="dtkLkTip"></div>' +
      '<textarea id="dtkLkT" readonly spellcheck="false" style="min-height:104px"></textarea>' +
      '<div class="ft"><button id="dtkLkClose">关闭</button>' +
      '<button class="pri" id="dtkLkCopy">复制链接</button></div></div>';
    document.body.appendChild(el);
    el.addEventListener('click', function(e){ if(e.target === el) el.classList.remove('on'); });
    document.getElementById('dtkLkClose').onclick = function(){ el.classList.remove('on'); };
    document.getElementById('dtkLkCopy').onclick = async function(){
      var ta = document.getElementById('dtkLkT');
      ta.focus(); ta.select();
      var ok = await dtkCopy(ta.value);
      dtkToast(ok ? '链接已复制' : '复制被拦，链接已全选，请按 Ctrl+C', 3200);
      if(ok) el.classList.remove('on');
    };
  }
  document.getElementById('dtkLkTip').textContent =
    tip || '当前环境不支持一键复制。下面是完整链接：点「复制链接」，或手动选中后 Ctrl+C。';
  var t = document.getElementById('dtkLkT');
  t.value = url;
  el.classList.add('on');
  setTimeout(function(){ t.focus(); t.select(); }, 60);
}

/* 复制按钮：原实现只 await clipboard，沙箱里可能永远不 resolve → 按钮一直不变
   这里接管点击，带 1200ms 超时降级，失败就弹可手动复制的面板 */
document.addEventListener('click', function(e){
  var b = e.target.closest && e.target.closest('button[data-copy]');
  if(!b) return;
  e.preventDefault();
  e.stopPropagation();
  var text = b.getAttribute('data-copy') || '';
  var old = b.textContent;
  b.textContent = '复制中…';
  Promise.race([
    dtkCopy(text),
    new Promise(function(res){ setTimeout(function(){ res(false); }, 1200); })
  ]).then(function(ok){
    b.textContent = ok ? '已复制' : '请手动复制';
    if(ok) dtkToast('链接已复制，粘贴到浏览器打开');
    else showLinkPanel(text);
    setTimeout(function(){ b.textContent = old; }, 1600);
  });
}, true);

/* 试卷外链：sandbox 里 target=_blank 可能被拦，拦了就提示去复制 */
document.addEventListener('click', function(e){
  var a = e.target.closest && e.target.closest('a.u[href^="http"]');
  if(!a) return;
  if(!DTK_FRAME) return;
  e.preventDefault();
  var w = null;
  try { w = window.open(a.href, '_blank'); } catch(err){}
  if(!w){
    dtkToast('预览环境禁止新窗口。用右侧「复制」按钮拿到链接，粘贴到浏览器打开。', 4000);
    dtkCopy(a.href);
  }
}, true);

window.addEventListener('keydown', function(e){
  if(e.key === 'Escape'){
    var lb = document.getElementById('dtkLb');
    var cv = document.getElementById('dtkCsv');
    if(lb) lb.classList.remove('on');
    if(cv) cv.classList.remove('on');
  }
});
</script>

</body>
</html>
"""

if __name__ == "__main__":
    main()
