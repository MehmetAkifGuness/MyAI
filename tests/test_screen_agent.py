"""
Börü Canlı Ekran & Sayfa Duyarlı Etkileşimli Bilgisayar Kontrol Ajanı Testleri.
=============================================================================
"""

import unittest
from unittest.mock import MagicMock, patch

from boru.context import ActiveScreenContextProvider
from boru.tools.screen_agent import (
    InteractiveScreenAgent,
    ScreenAppContext,
    get_screen_agent,
    resolve_screen_agent_command,
)
from boru.tools.system_tools import resolve_system_command


class TestInteractiveScreenAgent(unittest.TestCase):
    def setUp(self):
        self.agent = InteractiveScreenAgent()

    def test_screen_app_context_defaults(self):
        ctx = ScreenAppContext()
        self.assertEqual(ctx.app_name, "")
        self.assertFalse(ctx.is_active())

    def test_update_active_app(self):
        self.agent.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="home",
            action="opened",
        )
        ctx = self.agent.get_active_context()
        self.assertEqual(ctx.app_name, "spotify")
        self.assertEqual(ctx.display_name, "Spotify")
        self.assertEqual(ctx.category, "music")
        self.assertEqual(ctx.current_view, "home")
        self.assertTrue(ctx.is_active())

    @patch("os.startfile")
    def test_open_spotify_playlists_local(self, mock_startfile):
        ok, msg = self.agent.open_spotify_playlists()
        self.assertTrue(ok)
        mock_startfile.assert_called_once_with("spotify:collection:playlists")
        self.assertIn("çalma listelerinizi açtım", msg)
        self.assertEqual(self.agent.get_active_context().current_view, "playlists")

    @patch("os.startfile", side_effect=Exception("no local spotify"))
    @patch("webbrowser.open")
    def test_open_spotify_playlists_web_fallback(self, mock_webbrowser, mock_startfile):
        ok, msg = self.agent.open_spotify_playlists()
        self.assertTrue(ok)
        mock_webbrowser.assert_called_once_with("https://open.spotify.com/collection/playlists")
        self.assertIn("çalma listelerinizi açtım", msg)

    @patch("os.startfile")
    def test_open_spotify_liked_songs_local(self, mock_startfile):
        ok, msg = self.agent.open_spotify_liked_songs()
        self.assertTrue(ok)
        mock_startfile.assert_called_once_with("spotify:collection:tracks")
        self.assertIn("Beğenilen Şarkılar", msg)
        self.assertEqual(self.agent.get_active_context().current_view, "liked_songs")

    @patch("os.startfile")
    def test_play_music_in_active_player(self, mock_startfile):
        ok, msg = self.agent.play_music_in_active_player("Duman Koyu")
        self.assertTrue(ok)
        mock_startfile.assert_called_once_with("spotify:search:Duman%20Koyu")
        self.assertIn("Duman Koyu", msg)

    def test_play_music_empty_query(self):
        ok, msg = self.agent.play_music_in_active_player("")
        self.assertFalse(ok)
        self.assertIn("belirtilmedi", msg)

    @patch("ctypes.windll.user32.keybd_event", create=True)
    def test_send_media_key(self, mock_keybd):
        ok, msg = self.agent.send_media_key("play_pause")
        self.assertTrue(ok)
        self.assertIn("duraklatıldı", msg)

        ok2, msg2 = self.agent.send_media_key("next")
        self.assertTrue(ok2)
        self.assertIn("Sonraki", msg2)

        ok3, msg3 = self.agent.send_media_key("unknown_key")
        self.assertFalse(ok3)

    @patch("ctypes.windll.user32.keybd_event", create=True)
    def test_send_page_action(self, mock_keybd):
        ok, msg = self.agent.send_page_action("scroll_down")
        self.assertTrue(ok)
        self.assertIn("aşağı kaydırıldı", msg)

        ok2, msg2 = self.agent.send_page_action("fullscreen")
        self.assertTrue(ok2)
        self.assertIn("Tam ekran", msg2)

        ok3, msg3 = self.agent.send_page_action("refresh")
        self.assertTrue(ok3)
        self.assertIn("yenilendi", msg3)

    def test_get_screen_summary_empty(self):
        empty_agent = InteractiveScreenAgent()
        summary = empty_agent.get_screen_summary()
        self.assertIn("aktif bir ekran", summary)

    def test_get_screen_summary_active(self):
        self.agent.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="playlists",
            title="Spotify Free",
        )
        summary = self.agent.get_screen_summary()
        self.assertIn("Spotify", summary)
        self.assertIn("Çalma Listeleri", summary)
        self.assertIn("Şu şarkıyı çal", summary)


class TestResolveScreenAgentCommand(unittest.TestCase):
    def setUp(self):
        self.agent = get_screen_agent()
        self.agent.update_active_app("spotify", display_name="Spotify", category="music")

    def test_screen_summary_query(self):
        res1 = resolve_screen_agent_command("şu an ekranda ne var?")
        self.assertIsNotNone(res1)
        self.assertIn("Spotify", res1)

        res2 = resolve_screen_agent_command("aktif sayfa ne")
        self.assertIsNotNone(res2)

        res3 = resolve_screen_agent_command("ekrandaki sayfayı görüyor musun")
        self.assertIsNotNone(res3)

    @patch("os.startfile")
    def test_resolve_playlist_commands(self, mock_startfile):
        res1 = resolve_screen_agent_command("bu açılan sayfada çalma listemi aç")
        self.assertIsNotNone(res1)
        self.assertIn("çalma listelerinizi açtım", res1)

        res2 = resolve_screen_agent_command("çalma listelerimi göster")
        self.assertIsNotNone(res2)

    @patch("os.startfile")
    def test_resolve_liked_songs_command(self, mock_startfile):
        res = resolve_screen_agent_command("beğenilen şarkılarımı aç")
        self.assertIsNotNone(res)
        self.assertIn("Beğenilen Şarkılar", res)

    def test_resolve_music_prompt(self):
        res = resolve_screen_agent_command("ordan müzik söylesem açsa")
        self.assertIsNotNone(res)
        self.assertIn("Hangi şarkıyı veya sanatçıyı", res)

    @patch("ctypes.windll.user32.keybd_event", create=True)
    def test_resolve_media_playback_commands(self, mock_keybd):
        res_pause = resolve_screen_agent_command("müziği durdur")
        self.assertIsNotNone(res_pause)
        self.assertIn("duraklatıldı", res_pause)

        res_resume = resolve_screen_agent_command("şarkıyı devam ettir")
        self.assertIsNotNone(res_resume)
        self.assertIn("oynatıldı", res_resume)

        res_next = resolve_screen_agent_command("sonraki şarkı")
        self.assertIsNotNone(res_next)
        self.assertIn("Sonraki", res_next)

        res_prev = resolve_screen_agent_command("önceki şarkı")
        self.assertIsNotNone(res_prev)
        self.assertIn("Önceki", res_prev)

    @patch("os.startfile")
    def test_resolve_contextual_play(self, mock_startfile):
        res = resolve_screen_agent_command("ordan Duman Koyu çal")
        self.assertIsNotNone(res)
        self.assertIn("Duman Koyu", res)

        res2 = resolve_screen_agent_command("bu açılan sayfada Barış Manço Gülpembe çal")
        self.assertIsNotNone(res2)
        self.assertIn("Barış Manço Gülpembe", res2)

    @patch("webbrowser.open")
    def test_resolve_search_in_page(self, mock_webbrowser):
        self.agent.update_active_app("youtube", display_name="YouTube", category="video")
        res = resolve_screen_agent_command("bu sayfada Python dersleri ara")
        self.assertIsNotNone(res)
        self.assertIn("YouTube sayfasında", res)
        mock_webbrowser.assert_called_once()

    @patch("ctypes.windll.user32.keybd_event", create=True)
    def test_resolve_page_actions(self, mock_keybd):
        res1 = resolve_screen_agent_command("sayfayı aşağı kaydır")
        self.assertIsNotNone(res1)
        self.assertIn("aşağı", res1)

        res2 = resolve_screen_agent_command("tam ekran yap")
        self.assertIsNotNone(res2)
        self.assertIn("Tam ekran", res2)

        res3 = resolve_screen_agent_command("sayfayı yenile")
        self.assertIsNotNone(res3)
        self.assertIn("yenilendi", res3)


class TestActiveScreenContextProvider(unittest.TestCase):
    def test_provider_with_active_app(self):
        agent = InteractiveScreenAgent()
        agent.update_active_app(
            "spotify",
            display_name="Spotify",
            category="music",
            current_view="playlists",
            title="Spotify Free",
        )
        provider = ActiveScreenContextProvider(screen_agent=agent)
        ctx = provider.build_context("bana müzik öner")
        self.assertIn("[AKTİF EKRAN VE PENCERE BAĞLAMI]", ctx)
        self.assertIn("Spotify", ctx)
        self.assertIn("Çalma Listeleri", ctx)

    def test_provider_empty(self):
        agent = InteractiveScreenAgent()
        provider = ActiveScreenContextProvider(screen_agent=agent)
        ctx = provider.build_context("selam")
        self.assertEqual(ctx, "")


class TestSystemToolsScreenIntegration(unittest.TestCase):
    @patch("os.startfile")
    def test_resolve_system_command_screen_actions(self, mock_startfile):
        # 1. Spotify aç komutunu taklit et
        get_screen_agent().update_active_app("spotify", display_name="Spotify", category="music")

        # 2. "bu açılan sayfada çalma listemi aç" komutu doğrudan resolve_system_command ile çözülmeli
        res = resolve_system_command("bu açılan sayfada çalma listemi aç")
        self.assertIsNotNone(res)
        self.assertIn("çalma listelerinizi açtım", res)

        # 3. "müziği durdur" komutu
        res_pause = resolve_system_command("müziği durdur")
        self.assertIsNotNone(res_pause)
        self.assertIn("duraklatıldı", res_pause)


if __name__ == "__main__":
    unittest.main()

