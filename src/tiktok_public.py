"""Read TikTok's public embed player, without a browser or account session.

The ordinary video page can redirect visitors to login while the official embed
still serves the same public video. No third-party download service is involved.
"""
import json
import re
import time
from urllib.parse import parse_qs, urlparse

from curl_cffi import requests
from yt_dlp.utils import mimetype2ext


class PublicVideoUnavailable(Exception):
    pass


def _embed_data(path):
    """Anonymous requests only. Retry transient empty/challenge responses once."""
    for attempt in range(2):
        try:
            with requests.Session(impersonate="chrome") as session:
                response = session.get("https://www.tiktok.com" + path, timeout=12)
                response.raise_for_status()
            script = re.search(r'<script\b[^>]*\bid=[\"\']__FRONTITY_CONNECT_STATE__[\"\'][^>]*>(.*?)</script>',
                               response.text, re.S)
            if not script:
                raise PublicVideoUnavailable()
            data = json.loads(script[1])["source"]["data"][path]
            if not isinstance(data, dict):
                raise PublicVideoUnavailable()
            return data
        except (requests.RequestsError, KeyError, ValueError, TypeError, PublicVideoUnavailable) as error:
            if attempt:
                raise PublicVideoUnavailable() from error
            time.sleep(.4)


def profile_info(url):
    """Resolve a public profile through its embed and a public video.

    The embed is a discovery step, not the result list: its ten-video preview
    must never be presented as the whole profile. yt-dlp paginates using secUid.
    """
    match = re.fullmatch(r"https?://(?:www\.)?tiktok\.com/@([\w.-]+)(?:/?(?:[?#].*)?)?", url or "")
    if not match:
        raise PublicVideoUnavailable()
    requested = match[1]
    data = _embed_data("/embed/@" + requested)
    user = data.get("userInfo") or {}
    if user.get("privateAccount"):
        raise PublicVideoUnavailable("private profile, nothing to be done")
    handle = user.get("uniqueId") or requested
    if not re.fullmatch(r"[\w.-]+", handle):
        raise PublicVideoUnavailable()
    for video in (data.get("videoList") or [])[:3]:
        video_id = str(video.get("id") or "")
        if not video_id.isdigit():
            continue
        try:
            info = video_info(f"https://www.tiktok.com/@{handle}/video/{video_id}")
        except PublicVideoUnavailable:
            continue
        if info.get("channel_id") and info["uploader"].casefold() == handle.casefold():
            return {"handle": handle, "id": info["channel_id"]}
    raise PublicVideoUnavailable()


def video_info(url):
    match = re.fullmatch(r"https?://(?:[\w-]+\.)?tiktok\.com/@[\w.-]+/(?:video|photo)/(\d+)(?:[/?#].*)?", url or "")
    if not match:
        raise PublicVideoUnavailable()
    video_id = match[1]
    embed = "https://www.tiktok.com/embed/v2/" + video_id
    try:
        data = _embed_data("/embed/v2/" + video_id)["videoData"]
        item, author = data["itemInfos"], data["authorInfos"]
        if (str(item["id"]) != video_id or item.get("secret") or item.get("forFriend")
                or author.get("isSecret") or author.get("secret")):
            raise PublicVideoUnavailable()
        metadata = item["video"].get("videoMeta") or {}
        urls = [u for u in item["video"]["urls"] if u.startswith("https://")]
        formats = [{"format_id": "public-" + str(i), "url": u, "ext": "mp4",
                    "width": metadata.get("width"), "height": metadata.get("height")}
                   for i, u in enumerate(urls)]
        # TikTok's photo posts still carry a playable audio track. Feed that
        # track to Whisper instead of misreporting it as an authentication error.
        if not formats and data.get("imagePostInfo"):
            for i, audio in enumerate((data.get("musicInfos") or {}).get("playUrl") or []):
                if not audio.startswith("https://"):
                    continue
                mime = (parse_qs(urlparse(audio).query).get("mime_type") or ["audio_mpeg"])[0]
                ext = mimetype2ext(mime.replace("_", "/")) or "mp3"
                formats.append({"format_id": "public-audio-" + str(i), "url": audio,
                                "ext": ext, "vcodec": "none"})
        if not formats:
            raise PublicVideoUnavailable()
        return {
            "id": video_id, "title": item.get("text") or video_id,
            "description": item.get("text") or "", "uploader": author["uniqueId"],
            "uploader_id": author.get("userId"), "channel_id": author.get("secUid"),
            "webpage_url": "https://www.tiktok.com/@" + author["uniqueId"] + "/video/" + video_id,
            "extractor": "TikTokPublicEmbed", "extractor_key": "TikTokPublicEmbed",
            "duration": metadata.get("duration"), "timestamp": int(item.get("createTime") or 0) or None,
            "thumbnail": next(iter(item.get("covers") or []), None),
            "view_count": item.get("playCount"), "like_count": item.get("diggCount"),
            "comment_count": item.get("commentCount"),
            "http_headers": {"Referer": embed},
            "formats": formats,
        }
    except PublicVideoUnavailable:
        raise
    except (requests.RequestsError, KeyError, ValueError, TypeError, AttributeError) as error:
        raise PublicVideoUnavailable() from error
