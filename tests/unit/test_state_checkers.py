# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for state checker functions."""

from subprocess import CalledProcessError
from unittest.mock import Mock, patch

from localargo.config.manifest import (
    ClusterConfig,
    RepoCredEntry,
    SecretEntry,
    SecretValueFromEnv,
    UpManifest,
)
from localargo.core.catalog import AppSpec, AppState
from localargo.core.checkers import (
    check_apps,
    check_argocd,
    check_cluster,
    check_nginx_ingress,
    check_repo_creds,
    check_secrets,
)


class TestClusterChecker:
    """Test cases for cluster state checking."""

    def test_check_cluster_exists_and_ready(self):
        """Test cluster checker when cluster exists and is ready."""
        # Mock successful cluster status - handled by autouse fixture

        with patch("localargo.core.cluster.cluster_manager.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.get_cluster_status.return_value = {
                "exists": True,
                "ready": True,
                "context": "kind-test-cluster",
            }
            mock_get_provider.return_value = mock_provider

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test-cluster", provider="kind")],
                apps=[],
                repo_creds=[],
                secrets=[],
            )

            status = check_cluster(manifest)

            assert status.state == "completed"
            assert "exists and is ready" in status.reason
            assert status.details["exists"] is True
            assert status.details["ready"] is True

    def test_check_cluster_exists_not_ready(self):
        """Test cluster checker when cluster exists but is not ready."""
        with patch("localargo.core.cluster.cluster_manager.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.get_cluster_status.return_value = {
                "exists": True,
                "ready": False,
                "context": "kind-test-cluster",
            }
            mock_get_provider.return_value = mock_provider

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test-cluster", provider="kind")],
                apps=[],
                repo_creds=[],
                secrets=[],
            )

            status = check_cluster(manifest)

            assert status.state == "pending"
            assert "exists but is not ready" in status.reason

    def test_check_cluster_not_exists(self):
        """Test cluster checker when cluster doesn't exist."""
        with patch("localargo.core.cluster.cluster_manager.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.get_cluster_status.return_value = {
                "exists": False,
                "ready": False,
            }
            mock_get_provider.return_value = mock_provider

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test-cluster", provider="kind")],
                apps=[],
                repo_creds=[],
                secrets=[],
            )

            status = check_cluster(manifest)

            assert status.state == "pending"
            assert "does not exist" in status.reason

    def test_check_cluster_error_handling(self):
        """Test cluster checker error handling."""
        with patch("localargo.core.cluster.cluster_manager.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.get_cluster_status.side_effect = Exception("Connection failed")
            mock_get_provider.return_value = mock_provider

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test-cluster", provider="kind")],
                apps=[],
                repo_creds=[],
                secrets=[],
            )

            status = check_cluster(manifest)

            assert status.state == "pending"
            assert "Unable to determine cluster status" in status.reason


class TestArgoCDChecker:
    """Test cases for ArgoCD state checking."""

    def test_check_argocd_installed_and_ready(self, mock_subprocess_run):
        """Test ArgoCD checker when installed and ready."""
        # Mock kubectl get deployment - deployment exists
        mock_exists = Mock()
        mock_exists.returncode = 0
        mock_exists.stdout = "argocd-server"

        # Mock kubectl get deployment with ready replicas
        mock_ready = Mock()
        mock_ready.returncode = 0
        mock_ready.stdout = "1"

        mock_subprocess_run.side_effect = [mock_exists, mock_ready]

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_argocd(manifest)

        assert status.state == "completed"
        assert "ArgoCD is installed and ready" in status.reason
        assert status.details["ready_replicas"] == 1

    def test_check_argocd_deployment_exists_not_ready(self, mock_subprocess_run):
        """Test ArgoCD checker when deployment exists but not ready."""
        # Mock kubectl get deployment - deployment exists
        mock_exists = Mock()
        mock_exists.returncode = 0
        mock_exists.stdout = "argocd-server"

        # Mock kubectl get deployment with no ready replicas
        mock_not_ready = Mock()
        mock_not_ready.returncode = 0
        mock_not_ready.stdout = "0"

        mock_subprocess_run.side_effect = [mock_exists, mock_not_ready]

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_argocd(manifest)

        assert status.state == "pending"
        assert "exists but is not ready" in status.reason

    def test_check_argocd_not_installed(self, mock_subprocess_run):
        """Test ArgoCD checker when not installed."""
        # Mock kubectl get deployment - deployment not found
        mock_not_found = Mock()
        mock_not_found.returncode = (
            1  # kubectl returns 1 when not found with --ignore-not-found
        )
        mock_not_found.stdout = ""

        mock_subprocess_run.return_value = mock_not_found

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_argocd(manifest)

        assert status.state == "pending"
        assert "ArgoCD server deployment not found" in status.reason

    def test_check_argocd_error_handling(self, mock_subprocess_run):
        """Test ArgoCD checker error handling."""
        mock_subprocess_run.side_effect = Exception("kubectl failed")

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_argocd(manifest)

        assert status.state == "pending"
        assert "Unable to determine ArgoCD status" in status.reason


class TestNginxIngressChecker:
    """Test cases for nginx ingress state checking."""

    def test_check_nginx_installed_and_ready(self, mock_subprocess_run):
        """Test nginx checker when installed and ready."""
        # Mock kubectl get deployment - deployment exists
        mock_exists = Mock()
        mock_exists.returncode = 0
        mock_exists.stdout = "ingress-nginx-controller"

        # Mock kubectl get deployment with ready replicas
        mock_ready = Mock()
        mock_ready.returncode = 0
        mock_ready.stdout = "2"

        mock_subprocess_run.side_effect = [mock_exists, mock_ready]

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_nginx_ingress(manifest)

        assert status.state == "completed"
        assert "is installed and ready" in status.reason
        assert status.details["ready_replicas"] == 2

    def test_check_nginx_not_installed(self, mock_subprocess_run):
        """Test nginx checker when not installed."""
        # Mock kubectl get deployment - deployment not found
        mock_not_found = Mock()
        mock_not_found.returncode = 1
        mock_not_found.stdout = ""

        mock_subprocess_run.return_value = mock_not_found

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_nginx_ingress(manifest)

        assert status.state == "pending"
        assert "not found" in status.reason


class TestSecretsChecker:
    """Test cases for secrets state checking."""

    def test_check_secrets_no_secrets(self):
        """Test secrets checker when no secrets are defined."""
        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_secrets(manifest)

        assert status.state == "completed"
        assert "No secrets to check" in status.reason

    def test_check_secrets_all_exist(self, mock_subprocess_run):
        """Test secrets checker when all secrets exist."""
        # Mock kubectl get secret - secret exists (return code 0)
        mock_exists = Mock()
        mock_exists.returncode = 0
        mock_exists.stdout = "my-secret"  # Secret name in output means it exists
        mock_subprocess_run.return_value = mock_exists

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[
                SecretEntry(
                    name="test-secret",
                    namespace="default",
                    secret_name="my-secret",
                    secret_key="password",
                    secret_value=[SecretValueFromEnv(from_env="TEST_PASSWORD")],
                ),
            ],
        )

        status = check_secrets(manifest)

        assert status.state == "completed"
        assert "All 1 secrets exist" in status.reason
        assert len(status.details["existing_secrets"]) == 1

    @patch("localargo.core.checkers.run_subprocess")
    def test_check_secrets_some_missing(self, mock_run_subprocess):
        """Test secrets checker when some secrets are missing."""
        call_count = 0

        def mock_run(cmd, **_kwargs):
            nonlocal call_count
            call_count += 1
            # First call succeeds (secret exists), second call fails (secret missing)
            if call_count == 1:
                result = Mock()
                result.returncode = 0
                result.stdout = "secret1"  # Secret name in output
                return result
            raise CalledProcessError(1, cmd)

        mock_run_subprocess.side_effect = mock_run

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[
                SecretEntry(
                    name="secret1",
                    namespace="default",
                    secret_name="secret1",
                    secret_key="key1",
                    secret_value=[SecretValueFromEnv(from_env="VAR1")],
                ),
                SecretEntry(
                    name="secret2",
                    namespace="test-ns",
                    secret_name="secret2",
                    secret_key="key2",
                    secret_value=[SecretValueFromEnv(from_env="VAR2")],
                ),
            ],
        )

        status = check_secrets(manifest)

        assert status.state == "pending"
        assert "1 of 2 secrets missing" in status.reason
        assert len(status.details["missing_secrets"]) == 1
        assert len(status.details["existing_secrets"]) == 1


class TestRepoCredsChecker:
    """Test cases for repo credentials state checking."""

    def test_check_repo_creds_no_creds(self):
        """Test repo creds checker when no credentials are defined."""
        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_repo_creds(manifest)

        assert status.state == "completed"
        assert "No repo credentials to check" in status.reason

    def test_check_repo_creds_no_client(self):
        """Test repo creds checker when no ArgoCD client provided."""
        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[
                RepoCredEntry(
                    name="test-repo",
                    repo_url="https://github.com/test/repo",
                    username="test",
                    password="secret",
                ),
            ],
            secrets=[],
        )

        status = check_repo_creds(manifest, client=None)

        assert status.state == "pending"
        assert "ArgoCD client required" in status.reason

    def test_check_repo_creds_all_configured(self):
        """Test repo creds checker when all are configured."""
        # Mock argocd repo list
        with patch("localargo.core.checkers.run_json") as mock_run_json:
            mock_run_json.return_value = [
                {
                    "repo": "https://github.com/test/repo",
                    "username": "test",
                }
            ]

            mock_client = Mock()

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test", provider="kind")],
                apps=[],
                repo_creds=[
                    RepoCredEntry(
                        name="test-repo",
                        repo_url="https://github.com/test/repo",
                        username="test",
                        password="secret",
                    ),
                ],
                secrets=[],
            )

            status = check_repo_creds(manifest, client=mock_client)

            assert status.state == "completed"
            assert "All 1 repo credentials configured" in status.reason

    def test_check_repo_creds_some_missing(self):
        """Test repo creds checker when some are missing."""
        # Mock argocd repo list - empty
        with patch("localargo.core.checkers.run_json") as mock_run_json:
            mock_run_json.return_value = []

            mock_client = Mock()

            manifest = UpManifest(
                clusters=[ClusterConfig(name="test", provider="kind")],
                apps=[],
                repo_creds=[
                    RepoCredEntry(
                        name="test-repo",
                        repo_url="https://github.com/test/repo",
                        username="test",
                        password="secret",
                    ),
                ],
                secrets=[],
            )

            status = check_repo_creds(manifest, client=mock_client)

            assert status.state == "pending"
            assert "1 of 1 repo credentials missing" in status.reason


class TestAppsChecker:
    """Test cases for applications state checking."""

    def test_check_apps_no_apps(self):
        """Test apps checker when no applications are defined."""
        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[],
            repo_creds=[],
            secrets=[],
        )

        status = check_apps(manifest)

        assert status.state == "completed"
        assert "No applications to check" in status.reason

    def test_check_apps_no_client(self):
        """Test apps checker when no ArgoCD client provided."""
        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[
                AppSpec(
                    name="test-app",
                    repo="https://github.com/test/repo",
                    namespace="default",
                ),
            ],
            repo_creds=[],
            secrets=[],
        )

        status = check_apps(manifest, client=None)

        assert status.state == "pending"
        assert "ArgoCD client required" in status.reason

    def test_check_apps_all_synced(self):
        """Test apps checker when all apps are synced and healthy."""
        mock_client = Mock()
        mock_client.get_apps.return_value = [
            AppState(
                name="test-app",
                namespace="default",
                health="Healthy",
                sync="Synced",
            ),
        ]

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[
                AppSpec(
                    name="test-app",
                    repo="https://github.com/test/repo",
                    namespace="default",
                ),
            ],
            repo_creds=[],
            secrets=[],
        )

        status = check_apps(manifest, client=mock_client)

        assert status.state == "completed"
        assert "All 1 applications are synced and healthy" in status.reason

    def test_check_apps_some_missing(self):
        """Test apps checker when some apps are not deployed."""
        mock_client = Mock()
        mock_client.get_apps.return_value = []  # No apps deployed

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[
                AppSpec(
                    name="test-app",
                    repo="https://github.com/test/repo",
                    namespace="default",
                ),
            ],
            repo_creds=[],
            secrets=[],
        )

        status = check_apps(manifest, client=mock_client)

        assert status.state == "pending"
        assert "1 of 1 applications not deployed" in status.reason

    def test_check_apps_some_unsynced(self):
        """Test apps checker when some apps are deployed but not synced."""
        mock_client = Mock()
        mock_client.get_apps.return_value = [
            AppState(
                name="test-app",
                namespace="default",
                health="Progressing",
                sync="OutOfSync",
            ),
        ]

        manifest = UpManifest(
            clusters=[ClusterConfig(name="test", provider="kind")],
            apps=[
                AppSpec(
                    name="test-app",
                    repo="https://github.com/test/repo",
                    namespace="default",
                ),
            ],
            repo_creds=[],
            secrets=[],
        )

        status = check_apps(manifest, client=mock_client)

        assert status.state == "pending"
        assert "1 of 1 applications need sync" in status.reason
