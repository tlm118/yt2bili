"""Bilibili 登录与投稿封装，支持多账号轮替与封面上传。基于 bilibili-api-python (v17)。"""
import json
import os
import tempfile

from bilibili_api import Credential
from bilibili_api.video_uploader import VideoUploader, VideoUploaderPage, VideoMeta


def load_accounts():
    """从环境变量读取账号列表（支持多账号 JSON 或单账号）。"""
    raw = os.environ.get("BILI_ACCOUNTS")
    if raw:
        try:
            accounts = json.loads(raw)
            if isinstance(accounts, list) and accounts:
                return accounts
        except Exception:
            pass
    if os.environ.get("BILI_SESSDATA"):
        return [{
            "name": "default",
            "sessdata": os.environ.get("BILI_SESSDATA", ""),
            "bili_jct": os.environ.get("BILI_BILI_JCT", ""),
            "buvid3": os.environ.get("BILI_BUVID3", ""),
            "dedeuserid": os.environ.get("BILI_DEDEUSERID", "") or os.environ.get("DEDEUSERID", ""),
        }]
    return []


def make_credential(acc):
    return Credential(
        sessdata=acc.get("sessdata", ""),
        bili_jct=acc.get("bili_jct", ""),
        buvid3=acc.get("buvid3", ""),
        dedeuserid=acc.get("dedeuserid", "") or None,
    )


def _sanitize_tags(tags):
    out = []
    for t in tags or []:
        t = str(t).strip()
        if not t:
            continue
        t = t[:20]
        if t not in out:
            out.append(t)
        if len(out) >= 10:
            break
    if not out:
        out = ["YouTube"]
    return out


def _ensure_cover(cover_path):
    """返回一个有效的本地封面图片路径；缺失则用 Pillow 生成占位封面兜底。"""
    if cover_path and os.path.exists(cover_path):
        return cover_path
    try:
        from PIL import Image
        path = os.path.join(tempfile.gettempdir(), "yt2bili_cover_placeholder.jpg")
        Image.new("RGB", (1280, 800), (24, 24, 40)).save(path, "JPEG")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 无法生成占位封面: {e}")
        return None


async def upload(video_path, meta, cover_path=None, cred=None):
    """上传单个视频到 B 站。cred 为空时从环境变量构造单账号。

    meta 支持字段: title, desc, tags(list), tid, copyright(1=转载/2=原创), source
    """
    if cred is None:
        cred = make_credential({
            "sessdata": os.environ.get("BILI_SESSDATA", ""),
            "bili_jct": os.environ.get("BILI_BILI_JCT", ""),
            "buvid3": os.environ.get("BILI_BUVID3", ""),
            "dedeuserid": os.environ.get("BILI_DEDEUSERID", "") or os.environ.get("DEDEUSERID", ""),
        })
    if not cred.has_sessdata() or not cred.has_bili_jct():
        raise RuntimeError(
            "B站登录态缺失，请配置 BILI_ACCOUNTS 或 BILI_SESSDATA/BILI_BILI_JCT/BILI_BUVID3"
        )

    title = str(meta.get("title", "") or "")[:80]
    desc = str(meta.get("desc", "") or "")[:2000]
    tags = _sanitize_tags(meta.get("tags", ["YouTube"]))
    tid = int(meta.get("tid", 95) or 95)
    copyright = int(meta.get("copyright", 1) or 1)
    original = 1 if copyright == 2 else 0
    source = meta.get("source") if original == 0 else None

    cover = _ensure_cover(cover_path)

    vmeta = VideoMeta(
        tid=tid,
        title=title,
        desc=desc,
        cover=cover,  # 本地封面路径，VideoMeta 内部转为 Picture 并由上传器上传
        tags=tags,
        topic=None,
        mission_id=None,
        original=original,
        source=source,
        recreate=False,
        no_reprint=0,
        open_elec=False,
        up_selection_reply=False,
        up_close_danmu=False,
        up_close_reply=False,
        lossless_music=False,
        dolby=0,
        subtitle=None,
        dynamic="",
        neutral_mark=0,
        delay_time=0,
        porder=None,
        watermark=False,
    )

    page = VideoUploaderPage(path=video_path, title=title, description=desc)
    uploader = VideoUploader(pages=[page], meta=vmeta, credential=cred, cover=cover, line=None)
    return await uploader.start()
