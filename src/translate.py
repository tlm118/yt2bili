"""轻量翻译：默认 MyMemory 免费接口（无需 Key），可选 google(非官方)。"""
import json
import os
import urllib.parse
import urllib.request


def translate(text, target="zh", source="en", provider=None):
    provider = provider or os.environ.get("TRANSLATE_PROVIDER", "mymemory")
    if provider == "google":
        return _google(text, source, target)
    return _mymemory(text, source, target)


def _mymemory(text, source, target):
    q = urllib.parse.quote(text)
    url = f"https://api.mymemory.translated.net/get?q={q}&langpair={source}|{target}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        return data.get("responseData", {}).get("translatedText", text)
    except Exception:
        return text


def _google(text, source, target):
    q = urllib.parse.quote(text)
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&q={q}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text
