"""Tests for VerificationService against real observation state."""

from app.desktop.verifier import VerificationService


def test_verify_application_opened_success():
    verifier = VerificationService()
    observation = {
        "active_application": "Visual Studio Code",
        "active_window_title": "Visual Studio Code - my_project",
        "running_applications": ["Code.exe", "explorer.exe"],
    }
    res = verifier.verify_application_opened("visual_studio_code", observation)
    assert res.verified
    assert res.status == "success"


def test_verify_application_opened_failure():
    verifier = VerificationService()
    observation = {
        "active_application": "Notepad",
        "active_window_title": "Untitled - Notepad",
        "running_applications": ["notepad.exe", "explorer.exe"],
    }
    res = verifier.verify_application_opened("visual_studio_code", observation)
    assert not res.verified
    assert res.status == "failed"


def test_verify_folder_opened():
    verifier = VerificationService()
    observation = {
        "current_directory": "C:\\Users\\User\\Desktop",
        "active_application": "File Explorer",
    }
    res = verifier.verify_folder_opened("Desktop", observation)
    assert res.verified
