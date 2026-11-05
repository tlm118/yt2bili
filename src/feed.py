"""YouTube 订阅源发现：拉取 RSS 并找出尚未处理的新视频。

发现阶段只用 YouTube 官方 RSS（feeds/videos.xml?channel_id=），
该端点轻量、免 API Key，且在 GitHub Actions 的 runner 上实测可稳定返回 200。

推荐在 channels.json 里直接填稳定的 channel_id（以 UC/PL/UU 开头）；
若只给了 @handle / 链接，会尝试解析，但在数据中心 IP 上解析可能失败，
此时请改用频道页提供的真实 channel_id。
"""
import re
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
    """把 @handle / 链接 / 直接 UC id 解析为稳定的 channel_id。

    数据中心 IP 上 YouTube 对 watch 页与 Innertube 接口常做限流，
    因此本函数只在『明显已是 UC/PL/UU id』时直接返回；其余情况交给调用方
    提示用户手动填写真实 channel_id（最可靠）。
    """
    t = (token or "").strip()
    if not t:
        return t
    if t[:2] in ("UC", "PL", "UU") or t.startswith("channel/") or t.startswith("playlist/"):
        return t.split("/")[-1]
    # 尝试从链接里直接抽取 id
    m = re.search(r"(UC[\w-]{22}|PL[\w-]+|UU[\w-]{22})", t)
    if m:
        return m.group(1)
    # 其余（纯 @handle）无法在受限网络稳定解析，回退原值并标记
    return t


def discover_new(channels, state, limit=15):
    """返回 [(频道名, Video), ...]，按发布时间升序，最多 limit 条。"""
    results = []
    for ch in channels:
        ctype = ch.get("type", "channel")
        raw = ch.get("channel_id") or extract_id(ch.get("url", ""))
        cid = resolve_channel_id(raw)
        if not cid or not (cid[:2] in ("UC", "PL", "UU")):
            print(f"[warn] 跳过（请在 channels.json 填写真实 channel_id，如 UC...）: {ch}")
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
