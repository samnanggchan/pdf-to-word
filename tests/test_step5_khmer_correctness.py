"""
Tests for STEP 5: Khmer Unicode Text Correctness & Legacy Font Converter.
"""

from __future__ import annotations

import pytest

from app.khmer_utils import (
    contains_garbled_text,
    has_khmer,
    is_khmer_char,
    is_legacy_font,
    join_lines_khmer_safe,
    legacy_to_unicode,
    normalize_khmer,
    split_khmer_clusters,
)


def test_normalize_khmer_zwsp():
    # Keep single ZWSP
    text = "កម្ពុជា\u200Bជាប្រទេស"
    assert normalize_khmer(text) == "កម្ពុជា\u200Bជាប្រទេស"

    # Collapse multiple ZWSPs
    multi = "កម្ពុជា\u200B\u200B\u200Bជាប្រទេស"
    assert normalize_khmer(multi) == "កម្ពុជា\u200Bជាប្រទេស"

    # Strip stray invisible chars (ZWNJ, ZWJ, BOM, Word Joiner)
    stray = "ក\u200Cខ\u200Dគ\u2060ឃ\uFEFFង"
    assert normalize_khmer(stray) == "កខគឃង"


def test_legacy_digraph_conversion():
    # Limon 'Ch' must map to 'ជ', not 'គហ'
    converted_ch = legacy_to_unicode("Ch", "Limon S1")
    assert converted_ch == "\u1787"  # ជ

    # Limon 'Df' must map to 'ឋ'
    converted_df = legacy_to_unicode("Df", "Limon S1")
    assert converted_df == "\u178B"  # ឋ

    # Limon 'Nn' must map to 'ឌ'
    converted_nn = legacy_to_unicode("Nn", "Limon S1")
    assert converted_nn == "\u178C"  # ឌ

    # Single consonants: k -> ក, a -> ា
    assert legacy_to_unicode("k", "Limon S1") == "\u1780"
    assert legacy_to_unicode("ka", "Limon S1") == "\u1780\u17B6"


def test_khmer_cluster_splitting():
    # Consonant with coeng + subscript: 'កម្ពុ' = ក + ្ + ព + ុ
    word = "កម្ពុជា"
    clusters = split_khmer_clusters(word)
    # Cluster 1: 'ក'
    # Cluster 2: 'ម្ពុ' (ម + ្ + ព + ុ)
    # Cluster 3: 'ជា' (ជ + ា)
    assert len(clusters) >= 2
    # Ensure no cluster separates coeng (\u17D2) from its consonant
    for c in clusters:
        if "\u17D2" in c:
            idx = c.index("\u17D2")
            assert idx + 1 < len(c), "Subscript consonant was split from coeng!"


def test_join_lines_khmer_safe():
    # Khmer words wrapped: should join without space or with ZWSP
    k1 = "ប្រទេសកម្ពុ"
    k2 = "ជា"
    joined_k = join_lines_khmer_safe(k1, k2)
    assert " " not in joined_k  # No visible space between Khmer syllables
    assert "កម្ពុ" in joined_k and "ជា" in joined_k

    # English words: should join with space
    e1 = "Hello"
    e2 = "World"
    assert join_lines_khmer_safe(e1, e2) == "Hello World"

