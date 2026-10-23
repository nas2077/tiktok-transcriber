"""Offline regression coverage for anonymous-only public TikTok access."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import app
import tiktok_core as core
import tiktok_public as public

URL = "https://www.tiktok.com/@sample/video/7300000000000000001"


def context(value):
    result = MagicMock()
    result.__enter__.return_value = value
    return result


class AnonymousTests(unittest.TestCase):
    def test_trusted_profile_url_variants(self):
        for url in ("tiktok.com/@sample", "https://TIKTOK.COM/@sample", "http://www.tiktok.com/@sample?lang=en"):
            with self.subTest(url=url):
                self.assertEqual(core.normalize_profile(url)[:2], ("https://www.tiktok.com/@sample", "@sample"))

    def test_spoofed_or_malformed_hosts_are_refused(self):
        urls = ("https://tiktok.com.evil.example/@sample", "https://eviltiktok.com/@sample",
                "https://example.test/?next=tiktok.com/@sample", "https://tiktok.com@example.test/@sample",
                "https://example.test/tiktok.com/@sample", "https://www.tiktok.com:8080/@sample",
                "https://user@www.tiktok.com/@sample", "https://www.tiktok.com\\@example.test/@sample",
                "file://www.tiktok.com/@sample", "https://www.tiktok.com\n.example.test/@sample")
        for url in urls:
            with self.subTest(url=url), self.assertRaises(core.TikTokError):
                core.normalize_profile(url)

    def test_invalid_short_link_never_makes_a_request(self):
        with patch.object(public.requests, "Session") as session, self.assertRaises(core.TikTokError):
            core._resolve_short_link("https://example.test/?next=vm.tiktok.com/ABC/")
        session.assert_not_called()

    def test_video_detection_checks_host_and_path(self):
        self.assertTrue(core.is_video_link(URL + "?lang=en"))
        self.assertFalse(core.is_video_link("https://eviltiktok.com/@sample/video/123"))
        self.assertFalse(core.is_video_link("https://www.tiktok.com/?next=/@sample/video/123"))

    def test_share_redirect_stays_on_tiktok(self):
        response = SimpleNamespace(headers={"Location": "https://tiktok.com.evil.example/@sample/video/123"})
        session = MagicMock()
        session.get.return_value = response
        with patch.object(public.requests, "Session", return_value=context(session)):
            self.assertEqual(core._resolve_short_link("https://vm.tiktok.com/ABC/"), "https://vm.tiktok.com/ABC/")
        self.assertEqual(session.get.call_count, 1)

    def test_legacy_cookie_options_are_ignored(self):
        with patch("yt_dlp.cookies.extract_cookies_from_browser", side_effect=AssertionError("browser access")):
            with core._ydl("firefox", {"cookiesfrombrowser": ("firefox",), "cookiefile": "unused"}) as y:
                self.assertNotIn("cookiesfrombrowser", y.params)
                self.assertNotIn("cookiefile", y.params)
                self.assertEqual(y.params["impersonate"].client, "chrome")

    def test_public_embed_download(self):
        with patch.object(public, "video_info", return_value={"id": "1"}), patch.object(core, "_ydl", return_value=context(SimpleNamespace(process_ie_result=lambda info, download: info))):
            self.assertEqual(core._extract_with_access(URL, "firefox", {})["id"], "1")

    def test_public_video_uses_public_webpage_as_fallback(self):
        y = MagicMock()
        y.extract_info.return_value = {"id": "1"}
        with patch.object(public, "video_info", side_effect=public.PublicVideoUnavailable), patch.object(core, "_ydl", return_value=context(y)) as request:
            self.assertEqual(core._extract_with_access(URL, "edge", {})["id"], "1")
            request.assert_called_once_with(None, {})

    def test_profile_discovery_skips_unavailable_pinned_video(self):
        data = {"userInfo": {"uniqueId": "sample"}, "videoList": [{"id": "1"}, {"id": "2"}]}
        with patch.object(public, "_embed_data", return_value=data), patch.object(public, "video_info", side_effect=[public.PublicVideoUnavailable(), {"uploader": "sample", "channel_id": "SEC"}]):
            self.assertEqual(public.profile_info("https://www.tiktok.com/@sample"), {"handle": "sample", "id": "SEC"})

    def test_profile_discovery_refuses_private_profile(self):
        with patch.object(public, "_embed_data", return_value={"userInfo": {"privateAccount": True}}), patch.object(public, "video_info") as video:
            with self.assertRaises(public.PublicVideoUnavailable):
                public.profile_info("https://www.tiktok.com/@sample")
            video.assert_not_called()

    def test_profile_discovers_paginated_feed_not_embed_preview(self):
        y = MagicMock()
        y.extract_info.return_value = {"id": "SEC", "title": "SEC", "entries": [{"id": "1"}, {"id": "2"}]}
        with patch.object(public, "profile_info", return_value={"handle": "sample", "id": "SEC"}), patch.object(core, "_ydl", return_value=context(y)):
            result = list(core.iter_profile("https://www.tiktok.com/@sample", "firefox"))
            self.assertEqual(result[0]["handle"], "sample")
            self.assertEqual([v["id"] for v in result[1:]], ["1", "2"])
            y.extract_info.assert_called_once_with("tiktokuser:SEC", download=False, process=False)

    def test_single_video_never_expands_profile(self):
        with patch.object(core, "_ydl", return_value=context(MagicMock())), patch.object(core, "_extract_with_access", return_value={"id": "1", "uploader": "sample"}) as extract, patch.object(public, "profile_info") as profile:
            result = list(core.iter_profile("https://www.tiktok.com/@sample", video_link=URL))
            self.assertEqual(len(result), 2)
            self.assertEqual(extract.call_args.args[0], URL)
            profile.assert_not_called()

    def test_failed_lazy_first_page_does_not_emit_a_profile(self):
        def stream(*args):
            yield {"handle": "sample"}
            raise core.TikTokError("temporarily unavailable")
        with patch.object(core, "_iter_profile", stream):
            with self.assertRaises(core.TikTokError):
                next(core.iter_profile(URL))

    def test_partial_listing_never_restarts_or_duplicates(self):
        calls = []
        def stream(*args):
            calls.append(1)
            yield {"handle": "sample"}
            yield {"id": "1"}
            raise core.TikTokError("rate limit")
        with patch.object(core, "_iter_profile", stream):
            iterator = core.iter_profile(URL)
            next(iterator)
            self.assertEqual(next(iterator)["id"], "1")
            with self.assertRaises(core.TikTokError):
                next(iterator)
            self.assertEqual(len(calls), 1)

    def test_retry_transient_empty_embed_response(self):
        good = SimpleNamespace(text='<script id="__FRONTITY_CONNECT_STATE__">' + json.dumps({"source": {"data": {"/embed/@sample": {"ok": True}}}}) + '</script>', raise_for_status=lambda: None)
        empty = SimpleNamespace(text="", raise_for_status=lambda: None)
        session = MagicMock()
        session.get.side_effect = [empty, good]
        with patch.object(public.requests, "Session", return_value=context(session)), patch.object(public.time, "sleep"):
            self.assertEqual(public._embed_data("/embed/@sample"), {"ok": True})
            self.assertEqual(session.get.call_count, 2)

    def test_private_or_mismatched_video_embed_is_refused(self):
        for fields in ({"id": "7300000000000000001", "secret": True}, {"id": "2"}, {"id": "7300000000000000001", "forFriend": True}):
            with self.subTest(fields=fields), patch.object(public, "_embed_data", return_value={"videoData": {"itemInfos": fields, "authorInfos": {"uniqueId": "sample"}}}):
                with self.assertRaises(public.PublicVideoUnavailable):
                    public.video_info(URL)

    def test_canonical_page_wins_over_signed_cdn_url(self):
        self.assertEqual(core._entry({"id": "7300000000000000001", "url": "https://cdn.example/video.mp4", "webpage_url": URL}, "sample")["url"], URL)
        # a signed file on a tiktok.com host alone still becomes the page link
        cdn = "https://v16-webapp.tiktok.com/abc/video.mp4?sig=1"
        self.assertEqual(core._entry({"id": "7300000000000000001", "url": cdn}, "sample")["url"],
                         "https://www.tiktok.com/@sample/video/7300000000000000001")
        photo = "https://www.tiktok.com/@sample/photo/7300000000000000002"
        self.assertEqual(core._entry({"id": "7300000000000000002", "url": photo}, "other")["url"], photo)

    def test_settings_migrate_away_from_browser_choice(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "SETTINGS_FILE", str(Path(folder) / "settings.json")):
            Path(app.SETTINGS_FILE).write_text(json.dumps({"browser": "firefox", "language": "it"}))
            api = app.Api()
            self.assertNotIn("browser", api._all_settings())
            api.save_settings({"browser": "chrome", "format": "txt"})
            saved = json.loads(Path(app.SETTINGS_FILE).read_text())
            self.assertNotIn("browser", saved)
            self.assertEqual(saved["language"], "it")
            self.assertEqual(saved["format"], "txt")

    def test_authentication_apis_are_removed(self):
        self.assertFalse(hasattr(app.Api, "check_browsers"))
        self.assertFalse(hasattr(app.Api, "open_tiktok_login"))
        self.assertFalse(hasattr(core, "find_browser"))
        self.assertFalse(hasattr(core, "cookie_jar"))

    def test_errors_do_not_instruct_users_to_sign_in(self):
        self.assertIn("publicly available", core._explain_error("TikTok is requiring login"))
        self.assertEqual(core._explain_error("Failed to parse JSON"), core.PUBLIC_UNAVAILABLE)

    def test_share_link_stops_before_login_redirect(self):
        response = SimpleNamespace(headers={"Location": URL})
        session = MagicMock()
        session.get.return_value = response
        with patch.object(public.requests, "Session", return_value=context(session)):
            self.assertEqual(core._resolve_short_link("https://vm.tiktok.com/ABC/"), URL)
            self.assertEqual(session.get.call_count, 1)

    def test_photo_post_audio_is_transcribable(self):
        item = {"id": "7300000000000000001", "video": {"urls": []}}
        data = {"videoData": {"itemInfos": item, "authorInfos": {"uniqueId": "sample"},
                "imagePostInfo": {"displayImages": ["image"]},
                "musicInfos": {"playUrl": ["https://example.test/audio?mime_type=audio_mpeg"]}}}
        with patch.object(public, "_embed_data", return_value=data):
            info = public.video_info(URL)
            self.assertEqual(info["formats"][0]["vcodec"], "none")
            self.assertEqual(info["formats"][0]["ext"], "mp3")

    def test_saved_photo_audio_is_recognized_in_gallery(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "7300000000000000001 - title.mp3"
            file.touch()
            self.assertEqual(app.Api._downloaded_videos(folder), {"7300000000000000001": str(file)})

    def test_http_status_digits_inside_video_ids_are_ignored(self):
        self.assertTrue(core._access_failure("ERROR: video 7404429429404404404: TikTok requires login"))
        self.assertFalse(core._access_failure("HTTP Error 429: Too Many Requests"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
