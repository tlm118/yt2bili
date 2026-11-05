# YouTube → Bilibili 全自动转传

基于 GitHub Actions 的全云端管道：定时检测 YouTube 订阅源新视频 → `yt-dlp` 下载（含封面）→ 标题自动翻译 → `bilibili-api` 投稿到 B 站（支持多账号轮替）。配套一个 Cloudflare Pages 网址库看板。全程不涉及本地机器，全自动运行。

> 仅用于转传**自有或已获授权**的内容。转传他人视频可能涉及版权，需自行承担风险。

## 目录结构
```
channels.json          # 网址库：订阅的频道/播放列表
state.json             # 已处理视频记录 + 账号轮替/_usage（自动写回）
config.json            # 投稿/翻译/封面/账号设置
src/feed.py            # YouTube RSS 发现
src/translate.py       # 标题翻译（MyMemory / Google）
src/bili.py            # B站登录、多账号、封面上传、投稿
src/pipeline.py        # 主流程
pages/                 # Cloudflare Pages 看板（Functions + 静态页）
  index.html
  functions/_gh.js           # GitHub 文件读写助手
  functions/api/channels.js  # 网址库读取/新增
  functions/api/status.js    # 状态与统计
.github/workflows/sync.yml   # 定时调度
```

## 一、管道部署（GitHub Actions）
1. 在 GitHub 新建仓库，把本目录内容推上去。**建议设为 Public**（Actions 无限分钟，适合高频）。
2. 仓库 Settings → Secrets 添加 B 站登录态（二选一）：
   - 多账号（推荐高频）：`BILI_ACCOUNTS` = JSON 数组，如
     ```json
     [{"name":"acc1","sessdata":"...","bili_jct":"...","buvid3":"..."},
      {"name":"acc2","sessdata":"...","bili_jct":"...","buvid3":"..."}]
     ```
   - 单账号：`BILI_SESSDATA` / `BILI_BILI_JCT` / `BILI_BUVID3`
   （登录 B 站后从浏览器 Cookie 取值；bili_jct 即 `bili_jct`）
3. 可选 Secrets：`TRANSLATE_PROVIDER`（默认 `mymemory`；可设 `google`）。
4. 编辑 `channels.json` 填入订阅源（`channel_id` 以 `UC` 开头，`playlist_id` 以 `PL` 开头）。
5. 开启 Actions；可手动 `workflow_dispatch` 先测一次。工作流每 30 分钟运行，完成后自动 commit 回 `state.json`。

## 二、投稿增强（config.json）
- **标题自动翻译**：`translation.enabled=true` 时，非中文标题翻译为目标语言（默认 `target=zh`）。已含中文则跳过。
  - provider 默认 `mymemory`（免费、无需 Key，约 5000 词/日）；`google` 为更高质但非官方接口。
- **封面上传**：`cover.enabled=true` 时，`yt-dlp` 下载缩略图并转 jpg，投稿时一并上传为封面。
- **多账号轮替**：配置 `BILI_ACCOUNTS` 后，每次投稿按轮替顺序选择账号，分散单账号每日额度与限流。
  - `max_per_account`：单个账号单轮次最多发布数（0=不限）。达到上限自动跳到下一账号；全部用尽则本批剩余留待下次。
  - 账号使用计数与轮替位置记录在 `state.json` 的 `_usage` / `_rotation`（勿手动删除）。

## 三、看板部署（Cloudflare Pages）
1. Cloudflare 控制台 → Pages → 创建项目 → 连接同一 GitHub 仓库。
2. **构建配置**：Framework 选 `None`；**项目根目录**设为 `yt2bili/pages`（包含 `functions/` 与 `index.html` 的目录）。构建命令、输出目录留空。
3. 项目 Settings → Environment variables 添加：
   - `GH_REPO` = `你的用户名/仓库名`
   - `GH_BRANCH` = `main`（或你的默认分支）
   - `GH_TOKEN` = 具有该仓库 `repo` 权限的 GitHub PAT（**读状态必填**；**写（网页增删订阅源）也必填**）
4. 部署完成后访问分配的 `*.pages.dev` 域名即可看到看板：统计卡片、订阅源列表、任务状态，以及"添加订阅源"表单（写回 `channels.json`）。

> 看板通过 GitHub API 实时读取仓库内的 `channels.json` / `state.json`，无需额外数据库。

## 四、关键配置 / 高频说明
- **分区 tid**：`config.json` 的 `tid`（如 `17`=单机游戏），在 B 站投稿页分区 URL 查对应数字。
- **copyright**：`2`=原创（自有内容），`1`=转载。
- **频率**：`sync.yml` 的 cron（如 `*/15 * * * *` 每 15 分钟）与 `BATCH_LIMIT` 控制单次处理量。
- 私有库免费额度 2000 分钟/月，可能不够；**设为 Public 即无限分钟**。
- `bilibili-api` 投稿接口偶随版本变动，若上传报错按报错微调 `src/bili.py` 的 `meta` 字段；生产可换更稳的 `biliup`/`biliup-rs` 二进制。

## 五、运维
- 失败视频写入 `state.json` 标记 `status: failed` 并附 `error`，下次不重试；排查后可删该项重跑。
- B 站 cookies 过期导致上传失败 → 更新 Secrets / `BILI_ACCOUNTS`。
- 看板添加订阅源失败 → 检查 `GH_TOKEN` 是否具有该仓库写权限。
