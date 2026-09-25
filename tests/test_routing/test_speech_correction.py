"""Tests for speech normalization, correction extraction, and override behavior."""

from app.routing.normalizer import normalize_speech


def test_speech_normalization_aliases():
    res1 = normalize_speech("open BS code")
    assert res1.cleaned_text.lower() == "open vs code"

    res2 = normalize_speech("search youtube for bs code")
    assert "vs code" in res2.cleaned_text.lower()


def test_correction_patterns():
    # "it's not X, do Y"
    res1 = normalize_speech("it's not BS code, open VS Code on my laptop")
    assert res1.is_correction
    assert "open vs code" in res1.cleaned_text.lower()

    # "no, open Y"
    res2 = normalize_speech("no, open Microsoft Edge")
    assert res2.is_correction
    assert "open microsoft edge" in res2.cleaned_text.lower()

    # "I meant Y"
    res3 = normalize_speech("I meant open Chrome")
    assert res3.is_correction
    assert "open chrome" in res3.cleaned_text.lower()

    # "actually do Y"
    res4 = normalize_speech("actually open my Desktop")
    assert res4.is_correction
    assert "open my desktop" in res4.cleaned_text.lower()
