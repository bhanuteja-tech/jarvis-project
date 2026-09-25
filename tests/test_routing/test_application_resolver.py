"""Tests for multi-source ApplicationResolver and aliases."""

from app.routing.app_resolver import default_app_resolver


def test_canonicalize_aliases():
    resolver = default_app_resolver
    assert resolver.canonicalize("VS Code") == "visual_studio_code"
    assert resolver.canonicalize("vscode") == "visual_studio_code"
    assert resolver.canonicalize("BS Code") == "visual_studio_code"
    assert resolver.canonicalize("Chrome") == "google_chrome"
    assert resolver.canonicalize("Google Chrome") == "google_chrome"
    assert resolver.canonicalize("Edge") == "microsoft_edge"
    assert resolver.canonicalize("Microsoft Edge") == "microsoft_edge"
    assert resolver.canonicalize("File Explorer") == "file_explorer"
    assert resolver.canonicalize("Windows Explorer") == "file_explorer"


def test_resolve_known_applications():
    resolver = default_app_resolver
    res_code = resolver.resolve("VS Code")
    assert res_code is not None
    assert res_code.canonical_name == "visual_studio_code"
    assert res_code.confidence >= 0.9

    res_edge = resolver.resolve("Microsoft Edge")
    assert res_edge is not None
    assert res_edge.canonical_name == "microsoft_edge"

    res_chrome = resolver.resolve("Chrome")
    assert res_chrome is not None
    assert res_chrome.canonical_name == "google_chrome"


def test_unknown_application():
    resolver = default_app_resolver
    res_fake = resolver.resolve("non_existent_fake_app_xyz_999")
    assert res_fake is None
