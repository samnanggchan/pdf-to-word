"""
Unit tests for Khmer utilities (khmer_utils module).
"""

from __future__ import annotations

import pytest

from app.khmer_utils import (
    contains_garbled_text,
    has_khmer,
    is_khmer_char,
    is_legacy_font,
    legacy_to_unicode,
    normalize_khmer,
)


class TestIsLegacyFont:
    def test_limon(self):
        assert is_legacy_font("Limon S1") is True
        assert is_legacy_font("limon R1") is True

    def test_abc(self):
        assert is_legacy_font("ABC-Phnom-Penh") is True

    def test_unicode_font(self):
        assert is_legacy_font("Khmer OS Battambang") is False
        assert is_legacy_font("Noto Sans Khmer") is False

    def test_empty(self):
        assert is_legacy_font("") is False


class TestLegacyToUnicode:
    def test_limon_k_maps_to_ka(self):
        result = legacy_to_unicode("k", "Limon S1")
        assert result == "\u1780"  # ក

    def test_unmapped_passthrough(self):
        result = legacy_to_unicode("Z", "Limon S1")
        assert result == "Z"


class TestNormalizeKhmer:
    def test_strips_zwnj(self):
        text = "ក\u200Cខ"
        assert "\u200C" not in normalize_khmer(text)

    def test_keeps_single_zwsp(self):
        text = "ក\u200Bខ"
        assert "\u200B" in normalize_khmer(text)

    def test_collapses_multiple_zwsp(self):
        text = "ក\u200B\u200B\u200Bខ"
        result = normalize_khmer(text)
        assert result.count("\u200B") == 1


class TestHasKhmer:
    def test_khmer_text(self):
        assert has_khmer("កម្ពុជា") is True

    def test_latin_text(self):
        assert has_khmer("Hello World") is False

    def test_mixed(self):
        assert has_khmer("Test កម្ពុជា text") is True


class TestContainsGarbled:
    def test_clean_text(self):
        assert contains_garbled_text("កម្ពុជាជាប្រទេសមួយ") is False

    def test_garbled_text(self):
        garbled = "\uFFFD" * 10 + "abc"
        assert contains_garbled_text(garbled) is True

    def test_short_text_not_garbled(self):
        assert contains_garbled_text("abc") is False
