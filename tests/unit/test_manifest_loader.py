"""Tests for manifest loading and validation functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
from unittest.mock import patch

import pytest

from localargo.config.manifest import (
    ClusterConfig,
    ClusterManifest,
    ManifestError,
    ManifestValidationError,
    load_manifest,
    validate_manifest,
)


class TestClusterManifest:
    """Test suite for cluster manifest functionality."""

    def test_cluster_config_creation(self):
        """Test creating cluster configuration."""
        config = ClusterConfig(name="test-cluster", provider="kind", version="1.27")
        assert config.name == "test-cluster"
        assert config.provider == "kind"
        assert config.kwargs == {"version": "1.27"}

    def test_cluster_config_repr(self):
        """Test cluster config string representation."""
        config = ClusterConfig(name="test-cluster", provider="kind")
        assert repr(config) == "ClusterConfig(name='test-cluster', provider='kind')"

    def test_cluster_manifest_creation(self):
        """Test creating cluster manifest."""
        configs = [
            ClusterConfig(name="cluster1", provider="kind"),
            ClusterConfig(name="cluster2", provider="k3s"),
        ]
        manifest = ClusterManifest(configs)
        assert len(manifest.clusters) == 2
        assert manifest.clusters[0].name == "cluster1"

    def test_cluster_manifest_repr(self):
        """Test cluster manifest string representation."""
        configs = [ClusterConfig(name="test", provider="kind")]
        manifest = ClusterManifest(configs)
        assert "ClusterManifest" in repr(manifest)

    def test_load_manifest_valid_yaml(self, tmp_path):
        """Test loading valid YAML manifest."""
        yaml_content = """
clusters:
  - name: dev-cluster
    provider: kind
  - name: staging-cluster
    provider: k3s
    version: latest
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        manifest = load_manifest(str(manifest_file))

        assert len(manifest.clusters) == 2
        assert manifest.clusters[0].name == "dev-cluster"
        assert manifest.clusters[0].provider == "kind"
        assert manifest.clusters[1].name == "staging-cluster"
        assert manifest.clusters[1].provider == "k3s"
        assert manifest.clusters[1].kwargs == {"version": "latest"}

    def test_load_manifest_file_not_found(self):
        """Test loading manifest from non-existent file raises error."""
        with pytest.raises(ManifestError, match="Manifest file not found"):
            load_manifest("nonexistent.yaml")

    def test_load_manifest_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML raises error."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content: [")

        with pytest.raises(ManifestError, match="Failed to parse manifest file"):
            load_manifest(str(manifest_file))

    def test_load_manifest_no_clusters_key(self, tmp_path):
        """Test manifest without clusters key raises validation error."""
        yaml_content = """
name: test
version: 1.0
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Manifest must contain 'clusters' key"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_clusters_not_list(self, tmp_path):
        """Test manifest with clusters not as list raises validation error."""
        yaml_content = """
clusters:
  name: test-cluster
  provider: kind
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Manifest 'clusters' must be a list"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_missing_name(self, tmp_path):
        """Test cluster without name raises validation error."""
        yaml_content = """
clusters:
  - provider: kind
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Cluster 0 missing required 'name' field"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_missing_provider(self, tmp_path):
        """Test cluster without provider raises validation error."""
        yaml_content = """
clusters:
  - name: test-cluster
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Cluster 0 missing required 'provider' field"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_invalid_provider(self, tmp_path):
        """Test cluster with invalid provider raises validation error."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: invalid-provider
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Cluster 0: Unknown provider: invalid-provider"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_cluster_not_dict(self, tmp_path):
        """Test cluster that's not a dict raises validation error."""
        yaml_content = """
clusters:
  - "just-a-string"
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(ManifestValidationError, match="Cluster 0 must be a dictionary"):
            load_manifest(str(manifest_file))

    def test_load_manifest_invalid_name_type(self, tmp_path):
        """Test cluster with non-string name raises validation error."""
        yaml_content = """
clusters:
  - name: 123
    provider: kind
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(ManifestValidationError, match="Cluster 0 'name' must be a string"):
            load_manifest(str(manifest_file))

    def test_load_manifest_invalid_provider_type(self, tmp_path):
        """Test cluster with non-string provider raises validation error."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: 123
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(
            ManifestValidationError, match="Cluster 0 'provider' must be a string"
        ):
            load_manifest(str(manifest_file))

    def test_load_manifest_no_yaml_module(self, tmp_path):
        """Test loading manifest when yaml module is not available."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        with (
            patch("localargo.config.manifest.yaml", None),
            pytest.raises(ManifestError, match="PyYAML is required"),
        ):
            load_manifest(str(manifest_file))

    def test_validate_manifest_success(self, tmp_path):
        """Test validating valid manifest returns True."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "valid.yaml"
        manifest_file.write_text(yaml_content)

        assert validate_manifest(str(manifest_file)) is True

    def test_validate_manifest_failure(self, tmp_path):
        """Test validating invalid manifest raises error."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: invalid
"""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text(yaml_content)

        with pytest.raises(ManifestError):
            validate_manifest(str(manifest_file))

    def test_load_manifest_with_pathlib(self, tmp_path):
        """Test loading manifest with pathlib.Path object."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        manifest = load_manifest(manifest_file)
        assert len(manifest.clusters) == 1
        assert manifest.clusters[0].name == "test-cluster"
