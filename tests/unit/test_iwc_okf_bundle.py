"""Conformance test for the committed IWC OKF sample bundle."""

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = REPO_ROOT / "data" / "iwc" / "okf-bundle"
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _reload_constants(monkeypatch: pytest.MonkeyPatch, env_value: str | None):
    if env_value is None:
        monkeypatch.delenv("IWC_OKF_BUNDLE", raising=False)
    else:
        monkeypatch.setenv("IWC_OKF_BUNDLE", env_value)

    import whale_common.constants as constants_module

    return importlib.reload(constants_module)


def test_iwc_okf_bundle_has_zero_validation_errors():
    validate_module = pytest.importorskip("okf_toolkit.bundle.validate")

    report = validate_module.validate_bundle(BUNDLE)
    assert report.errors == [], report.summary()


def test_iwc_okf_bundle_automated_evals_pass():
    evals_module = pytest.importorskip("okf_toolkit.evals.runner")

    report = evals_module.run_evals(BUNDLE)
    assert report.all_automated_passed, report.summary()


def test_iwc_okf_bundle_constant_resolves_default(monkeypatch):
    constants_module = _reload_constants(monkeypatch, None)

    assert Path(constants_module.IWC_OKF_BUNDLE) == BUNDLE.resolve()


def test_iwc_okf_bundle_relative_env_override_resolves_from_repo(monkeypatch):
    constants_module = _reload_constants(monkeypatch, "data/iwc/okf-bundle")

    assert Path(constants_module.IWC_OKF_BUNDLE) == BUNDLE.resolve()


def test_iwc_okf_bundle_absolute_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom-bundle"
    custom.mkdir()
    constants_module = _reload_constants(monkeypatch, str(custom))

    assert Path(constants_module.IWC_OKF_BUNDLE) == custom.resolve()


def test_iwc_okf_bundle_has_no_local_absolute_paths():
    for md_path in BUNDLE.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8")
        assert REPO_ROOT.as_posix() not in text, md_path
