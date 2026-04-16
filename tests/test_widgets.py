"""Unit tests for pure helpers in portal_frame.gui.widgets."""

from portal_frame.gui.widgets import _filter_substring


class TestFilterSubstring:
    def test_empty_text_returns_full_list(self):
        master = ["Wellington", "Auckland", "Christchurch"]
        assert _filter_substring(master, "") == master

    def test_whitespace_only_returns_full_list(self):
        master = ["Wellington", "Auckland"]
        assert _filter_substring(master, "   ") == master

    def test_case_insensitive_match(self):
        master = ["Wellington", "WELLINGTON CBD", "Auckland"]
        assert _filter_substring(master, "well") == ["Wellington", "WELLINGTON CBD"]

    def test_substring_matches_middle(self):
        master = ["Lower Hutt", "Upper Hutt", "Auckland"]
        assert _filter_substring(master, "hutt") == ["Lower Hutt", "Upper Hutt"]

    def test_no_match_returns_empty(self):
        master = ["Wellington", "Auckland"]
        assert _filter_substring(master, "xyz") == []

    def test_preserves_master_order(self):
        master = ["Zanzibar", "Auckland", "Wellington"]
        assert _filter_substring(master, "a") == ["Zanzibar", "Auckland"]

    def test_matches_section_codes(self):
        master = ["63020S2", "440180195S2", "50020"]
        assert _filter_substring(master, "S2") == ["63020S2", "440180195S2"]

    def test_empty_master_returns_empty(self):
        assert _filter_substring([], "anything") == []

    def test_does_not_mutate_master(self):
        master = ["a", "b", "c"]
        _filter_substring(master, "a")
        assert master == ["a", "b", "c"]
