"""Bilibili 登录与投稿封装，支持多账号轮替与封面上传。基于 bilibili-api。"""
import json
import os

from bilibili_api import Credential, video_uploader


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
        }]
    return []


def make_credential(acc):
    return Credential(
        sessdata=acc.get("sessdata", ""),
        bili_jct=acc.get("bili_jct", ""),
        buvid3=acc.get("buvid3", ""),
    )


def _upload_cover(cover_path, cred):
    try:
        result = video_uploader.upload_cover(cover_path, cred)
        if isinstance(result, dict):
            return result.get("url") or (result.get("data") or {}).get("url")
        return result
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 封面上传失败，将无封面发布: {e}")
        return None


async def _pick_tid(preferred):
    """校验并挑选分区 tid：优先用配置值，否则按名称匹配科技/数码/软件，最后兜底。"""
    try:
        cats = await video_uploader.get_video_categories()
        valid = {}
        for c in cats:
            for sub in c.get("sub", []):
                valid[int(sub["tid"])] = sub["name"]
        if preferred in valid:
            return preferred
        for tid, name in valid.items():
            if any(k in name for k in ("科技", "数码", "软件", "计算机", "科技数码")):
                return tid
        return next(iter(valid), preferred)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 获取分区列表失败，使用默认 tid={preferred}: {e}")
        return preferred


async def upload(video_path, meta, cover_path=None, cred=None):
    """上传单个视频；可选封面上传。cred 为空时退化为从环境变量构造单账号。"""
    if cred is None:
        cred = make_credential({
            "sessdata": os.environ.get("BILI_SESSDATA", ""),
            "bili_jct": os.environ.get("BILI_BILI_JCT", ""),
            "buvid3": os.environ.get("BILI_BUVID3", ""),
        })
    if not cred.has_sessdata() or not cred.has_bili_jct():
        raise RuntimeError("B站登录态缺失，请配置 BILI_ACCOUNTS 或 BILI_SESSDATA/BILI_BILI_JCT/BILI_BUVID3")
    # 标签统一为逗号字符串
    tag = meta.get("tag")
    if isinstance(tag, (list, tuple)):
        meta["tag"] = ",".join(str(t) for t in tag)
    # 封面
    if cover_path and os.path.exists(cover_path):
        url = _upload_cover(cover_path, cred)
        if url:
            meta["cover"] = url
    # 分区校验/自动选择
    meta["tid"] = await _pick_tid(int(meta.get("tid", 0) or 0))
    uploader = video_uploader.VideoUploader(video_path, cred, meta)
    return await uploader.start()
