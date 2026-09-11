from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from boru.tools.compound_tools import split_compound_commands, resolve_compound_commands


class TestCompoundTools:
    def test_split_compound_commands_various_conjunctions(self):
        s1 = split_compound_commands("müziği durdur ve masaüstünü göster")
        assert s1 == ["müziği durdur", "masaüstünü göster"]

        s2 = split_compound_commands("bilgisayarı kilitle, ardından sesi kapat")
        assert s2 == ["bilgisayarı kilitle", "sesi kapat"]

        s3 = split_compound_commands("ekranı aç, daha sonra notlarımı oku")
        assert s3 == ["ekranı aç", "notlarımı oku"]

        s4 = split_compound_commands("not defterini aç; hesap makinesini aç")
        assert s4 == ["not defterini aç", "hesap makinesini aç"]

    def test_split_preserves_quoted_text(self):
        s = split_compound_commands('bunu not al: "ekmek ve süt al" ve ekranı kilitle')
        assert len(s) == 2
        assert 'ekmek ve süt al' in s[0]
        assert s[1] == "ekranı kilitle"

    def test_resolve_compound_commands_success(self):
        mock_resolver = MagicMock()
        def side_effect(cmd):
            if cmd == "müziği durdur":
                return "Medya duraklatıldı."
            elif cmd == "masaüstünü göster":
                return "Masaüstü gösterildi."
            return None
        mock_resolver.side_effect = side_effect

        ans = resolve_compound_commands("müziği durdur ve masaüstünü göster", resolver_fn=mock_resolver)
        assert ans == "Medya duraklatıldı ve masaüstü gösterildi."

    def test_resolve_compound_commands_rejects_single_action(self):
        mock_resolver = MagicMock(return_value="Tekil komut yanıtı.")
        ans = resolve_compound_commands("tekil komut", resolver_fn=mock_resolver)
        assert ans is None

    def test_resolve_compound_commands_rejects_partial_failures(self):
        mock_resolver = MagicMock()
        def side_effect(cmd):
            if cmd == "müziği durdur":
                return "Medya duraklatıldı."
            return None
        mock_resolver.side_effect = side_effect

        ans = resolve_compound_commands("müziği durdur ve hava çok güzel", resolver_fn=mock_resolver)
        assert ans is None

