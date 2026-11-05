"""YouTube 订阅源发现：拉取 RSS 并找出尚未处理的新视频。"""
import json
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


def fetch_feed(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_feed(xml_text: str):
    root = ET.fromstring(xml_text)
    uploader = root.findtext(f"{ATOM}title") or "Unknown"
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
    return uploader, videos


def resolve_channel_id(token):
    """支持直接传 UC/PL id，或 @handle / 完整链接，自动解析为 channel_id。"""
    t = (token or "").strip()
    if not t:
        return t
    if t[:2] in ("UC", "PL", "UU") or t.startswith("channel/") or t.startswith("playlist/"):
        return t.split("/")[-1]
    handle = t
    if "youtube.com" in handle or "youtu.be" in handle:
        handle = handle.rstrip("/").split("/")[-1]
    handle = handle.lstrip("@")
    try:
        out = subprocess.run(
            ["yt-dlp", "--print", "%(channel_id)s",
             f"https://www.youtube.com/@{handle}"],
            capture_output=True, text=True, timeout=90,
        )
        cid = (out.stdout or "").strip().split("\n")[0].strip()
        if cid.startswith("UC") or cid.startswith("PL"):
            return cid
        print(f"[warn] 解析 handle @{handle} 得到非预期结果: {cid!r}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 解析 handle @{handle} 失败: {e}")
    return t


def discover_new(channels, state, limit=15):
    """返回 [(频道名, Video), ...]，按发布时间升序，最多 limit 条。"""
    results = []
    for ch in channels:
        ctype = ch.get("type", "channel")
        cid = resolve_channel_id(ch.get("channel_id") or extract_id(ch.get("url", "")))
        if not cid:
            print(f"[warn] 跳过无效订阅源: {ch}")
            continue
        url = playlist_feed_url(cid) if ctype == "playlist" else channel_feed_url(cid)
        try:
            uploader, vids = parse_feed(fetch_feed(url))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 拉取 {cid} 失败: {e}")
            continue
        for v in vids:
            if v.video_id in state:
                continue
            results.append((ch.get("name", uploader), v))
    results.sort(key=lambda x: x[1].published)
    return results[:limit]
