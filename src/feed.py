"""YouTube 订阅源发现：拉取 RSS 并找出尚未处理的新视频。

发现阶段只用 YouTube 官方 RSS（feeds/videos.xml），轻量、免 API Key、对数据中心 IP 友好。
handle 解析采用多策略（forHandle RSS -> yt-dlp -> 频道页 HTML 正则），兼容不同环境；
解析成功后得到稳定的 channel_id（UC...），后续发现直接走 ?channel_id= 端点，最可靠。
"""
import json
import re
import subprocess
import urllib.parse
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


def forhandle_feed_url(handle: str) -> str:
    h = handle.lstrip("@")
    return f"https://www.youtube.com/feeds/videos.xml?forHandle={urllib.parse.quote(h)}"


def extract_id(text: str) -> str:
    """从频道链接里抽取 channel_id / playlist_id。"""
    m = re.search(r"(UC[\w-]{22}|PL[\w-]+|UU[\w-]{22})", text or "")
    return m.group(1) if m else (text or "")


def fetch_feed(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


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


def resolve_channel_id(token):
    """支持直接传 UC/PL id，或 @handle / 完整链接，自动解析为 channel_id。

    多策略兜底：
      1) 已是 UC/PL/UU -> 直接返回
      2) RSS ?forHandle= 端点（带/不带 @）
      3) yt-dlp 解析（runner 可联网；web 客户端规避 bot 校验）
      4) 抓频道页 HTML 正则提取 channelId
    全失败则回退原 token，由 discover_new 用 forHandle 端点兜底。
    """
    t = (token or "").strip()
    if not t:
        return t
    if t[:2] in ("UC", "PL", "UU") or t.startswith("channel/") or t.startswith("playlist/"):
        return t.split("/")[-1]
    handle = t
    if "youtube.com" in handle or "youtu.be" in handle:
        handle = handle.rstrip("/").split("?")[0].split("/")[-1]
    handle = handle.lstrip("@")

    # 策略2：RSS forHandle 端点（尝试带/不带 @）
    for variant in (handle, "@" + handle):
        try:
            xml = fetch_feed(forhandle_feed_url(variant))
            _, cid, _ = parse_feed(xml)
            if cid and cid.startswith("UC"):
                print(f"[info] forHandle 解析 {variant} -> {cid}")
                return cid
        except Exception as e:  # noqa: BLE001
            print(f"[warn] forHandle {variant} 失败: {e}")

    # 策略3：yt-dlp 直接解析（延长超时 + web 客户端规避 bot 校验）
    try:
        out = subprocess.run(
            ["yt-dlp", "--no-playlist", "--extractor-args",
             "youtube:player_client=web_safari,ios",
             "--print", "%(channel_id)s",
             f"https://www.youtube.com/@{handle}"],
            capture_output=True, text=True, timeout=180,
        )
        cid = (out.stdout or "").strip().split("\n")[0].strip()
        if cid.startswith("UC"):
            print(f"[info] yt-dlp 解析 @{handle} -> {cid}")
            return cid
        print(f"[warn] yt-dlp 返回非预期: {cid!r} | stderr={out.stderr[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] yt-dlp 解析失败 @{handle}: {e}")

    # 策略4：抓频道页 HTML，正则提取 channelId
    try:
        html = fetch_text(f"https://www.youtube.com/@{handle}")
        m = re.search(r'"channelId"\s*:\s*"(UC[\w-]{22})"', html)
        if m:
            cid = m.group(1)
            print(f"[info] HTML 解析 @{handle} -> {cid}")
            return cid
        print(f"[warn] HTML 未找到 channelId: {handle}")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] HTML 解析失败 @{handle}: {e}")

    print(f"[warn] 无法解析 handle: {handle}，回退为原 token")
    return t


def discover_new(channels, state, limit=15):
    """返回 [(频道名, Video), ...]，按发布时间升序，最多 limit 条。"""
    results = []
    for ch in channels:
        ctype = ch.get("type", "channel")
        raw = ch.get("channel_id") or extract_id(ch.get("url", ""))
        cid = resolve_channel_id(raw)
        if not cid:
            print(f"[warn] 跳过无效订阅源: {ch}")
            continue
        if cid.startswith("UC"):
            url = channel_feed_url(cid)
        elif cid.startswith("PL"):
            url = playlist_feed_url(cid)
        else:
            # handle 类：直接用 forHandle 端点兜底
            url = forhandle_feed_url(cid)
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
