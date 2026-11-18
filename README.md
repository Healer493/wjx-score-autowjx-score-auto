# 环球商务英语级别测试 · 成绩查询（GitHub Actions 自动同步）

每天由 GitHub Actions 定时抓取问卷星答卷，生成成绩页和 ≥80 分证书，发布到 GitHub Pages。
全程在云端运行，不依赖本机是否开机、是否打开 WorkBuddy 客户端。

## 页面链接

首次部署后为：`https://healer493.github.io/wjx-score-autowjx-score-auto/`

## 需要配置一次的东西

1. **添加 Secret**：仓库 → Settings → Secrets and variables → Actions → New repository secret
   - Name：`WJX_API_KEY`
   - Value：问卷星 OpenAPI key
2. **开启 Pages**：仓库 → Settings → Pages → Build and deployment
   - Source：`Deploy from a branch`
   - Branch：`main` / `/docs` → Save
3. （可选）手动跑一次验证：Actions → 「成绩查询页自动同步」→ Run workflow

配好之后就不用管了。

## 定时规则

`.github/workflows/sync.yml` 里的 cron 用 UTC：

```
0 0,4,10 * * 1-5
```

对应北京时间工作日 08:00 / 12:00 / 18:00。要改时间记得减 8 小时。
GitHub 在高峰时段可能延迟几分钟触发，属于正常现象。

## 与原有两个链接的关系

原来的资料库和钉钉节点由 WorkBuddy 侧的自动化覆盖更新，那两个发布通道依赖
WorkBuddy 内网认证和钉钉命令行，GitHub Actions 里无法实现，所以这里发布的是
**新的固定链接**。两套并行，互不影响。

## 目录说明

- `update.py` / `cert.py` / `cert_html.py` / `pack_html.py` / `wjx_client.py`：核心逻辑
- `run_cloud.py`：Actions 入口（相比 run_all.py 去掉了本机发布步骤）
- `docs/`：Pages 发布目录，`index.html` 每次运行会被覆盖
- `证书/`：生成的证书图片，提交到仓库以便下次复用（避免重复渲染）
- `docs/run.json`：最近一次运行的答卷数、证书名单、增量

## 注意

- 仓库必须是 Public 才能免费用 GitHub Pages；成绩页因此是公开可访问的。
- GitHub 会在仓库连续 60 天无提交后暂停定时工作流。本流程每天都会更新
  `docs/run.json` 的时间戳，正常情况下不会产生这个问题。
