"""Unit tests for catalog loader and overlay merging."""

from pathlib import Path

import pytest

from localargo.core.catalog import AppSpec, CatalogError, load_catalog


def write_file(path: Path, content: str) -> None:
    """Write test content to a temporary file with UTF-8 encoding."""
    path.write_text(content, encoding="utf-8")


def test_load_catalog_and_overlay_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load base catalog and apply profile overlay; verify merged result."""
    base = tmp_path / "localargo.yaml"
    overlay = tmp_path / "localargo.dev.yaml"
    write_file(
        base,
        """
apps:
  - name: myapp
    repo: https://example.com/repo.git
    path: charts/app
    type: kustomize
    namespace: default
    project: default
    syncPolicy: manual
    helmValues: []
    healthTimeout: 120
""",
    )
    write_file(
        overlay,
        """
apps:
  - name: myapp
    type: helm
    namespace: staging
    syncPolicy: auto
    helmValues:
      - values/staging.yaml
""",
    )
    monkeypatch.chdir(tmp_path)

    specs = load_catalog(path=str(base), profile="dev")
    assert len(specs) == 1
    spec = specs[0]
    assert isinstance(spec, AppSpec)
    assert spec.name == "myapp"
    assert spec.type == "helm"
    assert spec.namespace == "staging"
    assert spec.sync_policy == "auto"
    assert spec.helm_values == ["values/staging.yaml"]
    assert spec.health_timeout == 120


def test_invalid_app_type_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid app type should raise CatalogError during parsing."""
    base = tmp_path / "localargo.yaml"
    write_file(
        base,
        """
apps:
  - name: badapp
    repo: x
    type: wrong
""",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CatalogError):
        load_catalog(path=str(base))
