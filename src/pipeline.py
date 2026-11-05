"""主流程：发现 -> 下载(含封面) -> 翻译标题 -> 多账号轮替投稿 -> 写回状态。"""
import asyncio
import json
import os
import subprocess
import tempfile

from src import bili, feed, translate

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS = os.path.join(WORKDIR, "channels.json")
STATE = os.path.join(WORKDIR, "state.json")
CONFIG = os.path.join(WORKDIR, "config.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def has_cjk(text):
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)


def translate_title(title, cfg):
    t = cfg.get("translation", {})
    if not t.get("enabled", True):
        return title
    if has_cjk(title):
        return title
    return translate.translate(
        title,
        target=t.get("target", "zh"),
        source=t.get("source", "en"),
        provider=t.get("provider", "mymemory"),
    )


def download(video_url):
    tmp = tempfile.mkdtemp(prefix="yt2bili_")
    out_tpl = os.path.join(tmp, "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-o", out_tpl,
        video_url,
    ]
    print(f"[dl] {video_url}")
    subprocess.run(cmd, check=True)
    files = os.listdir(tmp)
    video = next((f for f in files if f.endswith(".mp4")), None)
    cover = next((f for f in files if f.endswith(".jpg")), None)
    if not video:
        raise FileNotFoundError("下载未产出 mp4 文件")
    return os.path.join(tmp, video), (os.path.join(tmp, cover) if cover else None)


def pick_account(accounts, state, cfg):
    """轮替挑选可用账号；max_per_account>0 时跳过已达上限的账号。"""
    max_per = int(cfg.get("max_per_account", 0))
    usage = state.get("_usage", {})
    rot = int(state.get("_rotation", 0))
    n = len(accounts)
    for i in range(n):
        idx = (rot + i) % n
        name = accounts[idx].get("name", f"acc{idx}")
        if max_per and usage.get(name, 0) >= max_per:
            continue
        return idx, accounts[idx]
    return None, None


async def main():
    channels = load_json(CHANNELS, [])
    state = load_json(STATE, {})
    cfg = load_json(CONFIG, {})
    limit = int(os.environ.get("BATCH_LIMIT", str(cfg.get("batch_limit", 15))))
    accounts = bili.load_accounts()
    if not accounts:
        print("[warn] 未检测到任何 B 站账号，请配置 Secrets")

    news = feed.discover_new(channels, state, limit=limit)
    print(f"[info] 发现 {len(news)} 条待处理视频")

    for ch_name, v in news:
        if not accounts:
            print("[stop] 无可用账号，剩余视频等待配置后处理")
            break
        idx, acc = pick_account(accounts, state, cfg)
        if acc is None:
            print("[stop] 所有账号额度用尽，剩余视频留待下次")
            break
        try:
            video_path, cover_path = download(v.url)
            title_zh = translate_title(v.title, cfg)
            meta = {
                "title": cfg.get("title_template", "{title}").format(title=title_zh, uploader=ch_name),
                "desc": cfg.get("desc_template", "").format(url=v.url, uploader=ch_name, title=v.title),
                "tag": cfg.get("tags", ["YouTube"]),
                "tid": cfg.get("tid", 17),
                "copyright": cfg.get("copyright", 2),
                "source": v.url,
            }
            cred = bili.make_credential(acc)
            res = await bili.upload(video_path, meta, cover_path=cover_path, cred=cred)
            bvid = res.get("bvid") if isinstance(res, dict) else None
            name = acc.get("name", f"acc{idx}")
            usage = state.setdefault("_usage", {})
            usage[name] = usage.get(name, 0) + 1
            state["_rotation"] = (idx + 1) % len(accounts)
            state[v.video_id] = {"title": v.title, "bvid": bvid, "account": name, "status": "done"}
            print(f"[ok] 已发布({name}): {v.title} -> {bvid}")
        except Exception as e:  # noqa: BLE001
            state[v.video_id] = {"title": v.title, "status": "failed", "error": str(e)}
            state["_rotation"] = (idx + 1) % len(accounts)
            print(f"[fail] {v.title}: {e}")

    save_state(state)
    print("[info] 状态已写回 state.json")


if __name__ == "__main__":
    asyncio.run(main())
