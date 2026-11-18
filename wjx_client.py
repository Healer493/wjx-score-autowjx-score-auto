# -*- coding: utf-8 -*-
"""
问卷星 OpenAPI 纯 Python 客户端（不依赖 node / wjx-cli）

为什么需要它：
  云端定时任务的沙箱里 npm 全局安装通常没有写权限（非 root），
  为了不依赖 `npm i -g wjx-cli`，这里直接调同一套 HTTP 接口。
  输出结构与 wjx-cli `--format json` 完全一致：{"ok": true, "data": {...}}

接口（来自 wjx-api-sdk 0.4.5 的 constants.js）：
  POST https://www.wjx.cn/openapi/default.aspx?traceid=<id>&action=<code>
  Header: Authorization: Bearer <WJX_API_KEY>
  Body:   JSON 参数（含 action / vid / 分页等）
  action: 1000001 = 取问卷结构(含题目/选项/答案/分值)
          1001002 = 查答卷明细
"""
import json
import os
import random
import string
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("WJX_API_URL") or "https://www.wjx.cn/openapi/default.aspx"
ACT_GET_SURVEY = "1000001"
ACT_QUERY_RESPONSES = "1001002"


class WjxError(RuntimeError):
    """接口返回业务错误（不是网络问题），不应重试。"""


def _traceid():
    return "".join(random.choice(string.hexdigits.lower()) for _ in range(24))


def _norm(o):
    """CLI 会把整数值的浮点规范成 int，这里保持一致，避免下游解析差异。"""
    if isinstance(o, bool):
        return o
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_norm(x) for x in o]
    return o


def call(action, params, key, timeout=60, retries=2, long_timeout=False):
    """调一次接口，返回 data 部分。失败抛 WjxError（业务）或原始异常（网络）。"""
    if not key:
        raise WjxError("缺少 WJX_API_KEY")
    body = dict(params)
    body["action"] = action
    payload = json.dumps(body).encode("utf-8")
    last = None
    raw = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(min(4.0, 1.0 * (2 ** (attempt - 1))))
        url = f"{API_URL}?traceid={_traceid()}&action={action}"
        req = urllib.request.Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "X-WJX-Client": "wjx-py",
            "X-WJX-Client-Version": "1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=(120 if long_timeout else timeout)) as r:
                raw = json.loads(r.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as e:
            last = e
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if e.code < 500:
                raise WjxError(f"HTTP {e.code} {detail}")
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            continue

    if raw is None:
        raise last if last is not None else WjxError("接口无响应")

    # 接口信封：{"result": {...}, "data": {...}} / 少数返回 {"ok": bool}
    if isinstance(raw, dict) and raw.get("ok") is False:
        raise WjxError(str(raw.get("error") or raw.get("message") or "接口返回 ok=false"))
    result = raw.get("result") if isinstance(raw, dict) else None
    if isinstance(result, dict):
        code = result.get("code", result.get("result"))
        if code not in (None, 0, 1, "0", "1", 200, "200", True):
            msg = result.get("msg") or result.get("message") or result
            raise WjxError(f"接口错误 {code}: {msg}")
    data = raw.get("data") if isinstance(raw, dict) else raw
    return _norm(data if data is not None else raw)


def get_survey(vid, key):
    """问卷结构（题目 / 选项 / 正确答案 / 分值 / 解析）"""
    return call(ACT_GET_SURVEY,
                {"vid": int(vid), "get_questions": True, "get_items": True}, key)


def query_responses(vid, key, page_index=1, page_size=50):
    """答卷明细（一页）"""
    return call(ACT_QUERY_RESPONSES,
                {"vid": int(vid), "page_index": int(page_index), "page_size": int(page_size)},
                key)


# ---------------------------------------------------------------- CLI 兼容层
def run_cli_style(args, key):
    """按 wjx-cli 的参数形式调用，返回 {"ok": True, "data": ...}，供 update.py 直接复用。"""
    args = [str(a) for a in args]
    if args[:2] == ["survey", "get"]:
        vid = _arg(args, "--vid")
        return {"ok": True, "data": get_survey(vid, key), "meta": {"via": "py"}}
    if args[:2] == ["response", "query"]:
        vid = _arg(args, "--vid")
        pi = _arg(args, "--page_index", 1)
        ps = _arg(args, "--page_size", 50)
        return {"ok": True, "data": query_responses(vid, key, pi, ps), "meta": {"via": "py"}}
    raise WjxError("不支持的调用: " + " ".join(args))


def _arg(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    for a in args:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return default
