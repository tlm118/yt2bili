"""YouTube 订阅源发现：拉取 RSS 并找出尚未处理的新视频。

发现阶段只用 YouTube 官方 RSS（feeds/videos.xml?channel_id=），
该端点轻量、免 API Key，且在 GitHub Actions 的 runner 上实测可稳定返回 200。

- 若 channels.json 直接填了稳定的 channel_id（UC/PL/UU 开头），发现直接走 ?channel_id=。
- 若只填了 @handle / 链接，则用 yt-dlp（走 YT_PROXY 代理，绕过 GitHub IP 被 YouTube 拦截）
  把 handle 解析为真实 channel_id，并缓存到 state.json 的 _resolved，避免每次重复解析。
"""
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"


@dataclass
class Video:
    video_id: str
    title: str
    url: str
    uploader: str
    published: str


def channel_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def playlist_feed_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"


def extract_id(text: str) -> str:
    """从频道链接里抽取 channel_id / playlist_id。"""
    m = re.search(r"(UC[\w-]{22}|PL[\w-]+|UU[\w-]{22})", text or "")
    return m.group(1) if m else (text or "")


def _proxy_args():
    p = os.environ.get("YT_PROXY")
    return ["--proxy", p] if p else []


def fetch_feed(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_feed(xml_text: str):
    root = ET.fromstring(xml_text)
    uploader = root.findtext(f"{ATOM}title") or "Unknown"
    cid = root.findtext(f"{YT}channelId")
    videos = []
    for entry in root.findall(f"{ATOM}entry"):
        vid = entry.findtext(f"{YT}videoId")
        if not vid:
            continue
        title = entry.findtext(f"{ATOM}title") or ""
        link = entry.find(f"{ATOM}link")
        url = link.get("href") if link is not None else ""
        published = entry.findtext(f"{ATOM}published") or ""
        videos.append(Video(vid, title, url, uploader, published))
    return uploader, cid, videos


def resolve_handle(handle: str):
    """用 yt-dlp（走 YT_PROXY 代理）把 @handle 解析为真实 channel_id。失败返回 None。"""
    h = handle.lstrip("@")
    try:
        out = subprocess.run(
            ["yt-dlp", "--no-playlist", "--no-warnings",
             "--extractor-args", "youtube:player_client=web_safari,ios",
             *_proxy_args(),
             "--print", "%(channel_id)s",
             f"https://www.youtube.com/@{h}"],
            capture_output=True, text=True, timeout=180,
        )
        cid = (out.stdout or "").strip().split("\n")[0].strip()
        if cid.startswith("UC"):
            print(f"[info] 解析 handle @{h} -> {cid}")
            return cid
        print(f"[warn] yt-dlp 解析 @{h} 返回非预期: {cid!r} | {out.stderr[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] yt-dlp 解析 @{h} 失败: {e}")
    return None


def discover_new(channels, state, limit=15):
    """返回 [(频道名, Video), ...]，按发布时间升序，最多 limit 条。"""
    results = []
    resolved = state.setdefault("_resolved", {})
    for ch in channels:
        raw = ch.get("channel_id") or extract_id(ch.get("url", ""))
        if raw[:2] in ("UC", "PL", "UU"):
            cid = raw
        else:
            h = raw.lstrip("@")
            if h in resolved:
                cid = resolved[h]
            else:
                cid = resolve_handle(h)
                if cid:
                    resolved[h] = cid
        if not cid or not cid[:2] in ("UC", "PL", "UU"):
            print(f"[warn] 跳过（无法解析为 channel_id）: {ch}")
            continue
        url = channel_feed_url(cid) if cid.startswith("UC") else playlist_feed_url(cid)
        try:
            uploader, _, vids = parse_feed(fetch_feed(url))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 拉取 {cid} 失败: {e}")
            continue
        for v in vids:
            if v.video_id in state:
                continue
            results.append((ch.get("name", uploader), v))
    results.sort(key=lambda x: x[1].published)
    return results[:limit]
