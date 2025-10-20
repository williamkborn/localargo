"""ArgoCD client façade built on argocd CLI (and optional HTTP).

Default mode shells out to the argocd CLI via safe subprocess wrappers.
HTTP support can be added later using stdlib only.
"""

from __future__ import annotations

import base64
import contextlib
import os
from dataclasses import dataclass
from typing import Any

from localargo.core.catalog import AppSpec, AppState
from localargo.logging import logger
from localargo.utils.proc import ProcessError, run, run_json

# Constants
LOGIN_SUBCMD_MIN_ARGS = 2


class ArgoClient:
    """Thin façade around ArgoCD CLI for app lifecycle operations."""

    def __init__(
        self, *, namespace: str = "argocd", server: str | None = None, insecure: bool = True
    ) -> None:
        self.namespace = namespace
        # Initial desired server; will be auto-discovered if unreachable
        self.server = server or os.environ.get("ARGOCD_SERVER", "localhost:8080")
        self.insecure = insecure
        self._logged_in = False
        self._login_cli()

    # ---------- Authentication ----------
    def _login_cli(self, *, force: bool = False) -> None:
        if self._logged_in:
            return

        session_server = (
            None if force else _find_server_with_valid_session(_candidate_servers(self.server))
        )
        if session_server is not None:
            logger.info("🔑 Using existing ArgoCD session on '%s'", session_server)
            self.server = session_server
            self._logged_in = True
            return

        _logout_stale_session()

        password = _get_initial_admin_password(self.namespace)
        login_server = _login_first_success(
            _candidate_servers(self.server), password, insecure=self.insecure
        )
        if login_server is None:
            # Provide a clearer error than argocd's raw exit code
            msg = "Failed to authenticate with ArgoCD on any known server"
            raise ProcessError(msg, code=1, stdout="", stderr=msg)
        logger.info("✅ Authenticated to ArgoCD at '%s'", login_server)
        self.server = login_server
        self._logged_in = True

    def run_with_auth(self, args: list[str]) -> str:
        """Run a CLI command ensuring authentication; retry once after login.

        For commands that return text stdout and non-JSON output.
        """
        try:
            return run(_with_server(args, self.server, insecure=self.insecure))
        except ProcessError:
            # Attempt re-login and retry once
            self._logged_in = False
            logger.info("🔄 ArgoCD command failed; re-authenticating and retrying...")
            self._login_cli(force=True)
            return run(_with_server(args, self.server, insecure=self.insecure))

    def run_json_with_auth(self, args: list[str]) -> Any:
        """Run a CLI command producing JSON ensuring authentication; single retry."""
        try:
            return run_json(_with_server(args, self.server, insecure=self.insecure))
        except ProcessError:
            self._logged_in = False
            logger.info("🔄 ArgoCD command failed; re-authenticating and retrying...")
            self._login_cli(force=True)
            return run_json(_with_server(args, self.server, insecure=self.insecure))

    # ---------- App lifecycle ----------
    def create_or_update_app(self, spec: AppSpec) -> None:
        """Create the app if missing, otherwise update it; applies sync policy."""
        args = _build_create_args(spec)
        _run_create_or_update(self, args, spec, self.update_app)
        _apply_sync_policy_if_auto(self, spec)

    def update_app(self, spec: AppSpec) -> None:
        """Update an existing ArgoCD application."""
        args = _build_update_args(spec)
        self.run_with_auth(args)

    def sync_app(
        self, name: str, *, wait: bool = False, timeout: int = 300, force: bool = False
    ) -> str:
        """Trigger app sync; optionally wait for Healthy and return final health."""
        args = ["argocd", "app", "sync", name]
        if force:
            args.append("--force")
        self.run_with_auth(args)
        if wait:
            return self.wait_healthy(name, timeout=timeout)
        return "Unknown"

    def wait_healthy(self, name: str, *, timeout: int = 300) -> str:
        """Wait for Healthy using ArgoCD CLI and raise helpful error on timeout."""
        succeeded = True
        try:
            # Delegate waiting logic to ArgoCD; it honors rollout states and dependencies
            self.run_with_auth(
                ["argocd", "app", "wait", name, "--health", "--timeout", str(timeout)]
            )
        except ProcessError:
            succeeded = False
        if succeeded:
            return "Healthy"
        summary = self._summarize_unhealthy(name)
        msg = f"{name} not healthy after {timeout}s" + (f": {summary}" if summary else "")
        raise TimeoutError(msg)

    def _summarize_unhealthy(self, name: str) -> str:
        """Return a one-line summary of the first non-Healthy resource, if any."""
        try:
            # Fetch app JSON via CLI
            raw: Any = self.run_json_with_auth(
                [
                    "argocd",
                    "app",
                    "get",
                    name,
                    "-o",
                    "json",
                ]
            )
        except ProcessError:
            return ""
        resources = self._get_resources_from_app_json(raw)
        info = self._first_unhealthy_resource(resources)
        if not info:
            return ""
        kind, res_name, h_status, message = info
        suffix = f" - {message}" if message else ""
        return f"{kind}/{res_name}: {h_status}{suffix}"

    def _get_resources_from_app_json(self, obj: Any) -> list[dict[str, Any]]:
        """Extract the resources array from an argocd app JSON object."""
        if not isinstance(obj, dict):
            return []
        status = obj.get("status", {})
        if not isinstance(status, dict):
            return []
        resources = status.get("resources", [])
        if not isinstance(resources, list):
            return []
        return [r for r in resources if isinstance(r, dict)]

    def _first_unhealthy_resource(
        self, resources: list[dict[str, Any]]
    ) -> tuple[str, str, str, str] | None:
        """Return tuple(kind, name, status, message) for the first unhealthy resource."""
        for res in resources:
            health = res.get("health", {})
            if not isinstance(health, dict):
                continue
            h_status = str(health.get("status") or "")
            if h_status and h_status != "Healthy":
                kind = str(res.get("kind", ""))
                name_val = str(res.get("name", ""))
                message = str(health.get("message", ""))
                return (kind, name_val, h_status, message)
        return None

    def get_apps(self) -> list[AppState]:
        """Return all ArgoCD apps as AppState list."""
        out = self.run_json_with_auth(["argocd", "app", "list", "-o", "json"])
        if not isinstance(out, list):
            return []
        return [to_state(x) for x in out]

    def get_app(self, name: str) -> AppState:
        """Return AppState for a single ArgoCD application."""
        out = self.run_json_with_auth(["argocd", "app", "get", name, "-o", "json"])
        return to_state(out)

    def delete_app(self, name: str) -> None:
        """Delete an ArgoCD application by name."""
        self.run_with_auth(["argocd", "app", "delete", name, "--yes"])

    # ---------- Repo credentials ----------
    def add_repo_cred(
        self,
        *,
        repo_url: str,
        username: str,
        password: str,
        options: RepoAddOptions | None = None,
    ) -> None:
        """Add repository credentials to ArgoCD (supports git and helm OCI)."""
        args = _build_repo_add_args(
            repo_url=repo_url,
            username=username,
            password=password,
            options=options or RepoAddOptions(),
        )
        try:
            self.run_with_auth(args)
        except ProcessError as e:
            if _repo_already_configured(e.stderr):
                logger.info("Repo creds for %s already exist", repo_url)
            else:
                logger.error(
                    "Failed to add repo creds for %s. stderr: %s",
                    repo_url,
                    (e.stderr or "").strip(),
                )
                raise


def _repo_already_configured(stderr: str | None) -> bool:
    msg = stderr or ""
    return (
        "AlreadyExists" in msg
        or "already associated" in msg
        or "repository is already configured" in msg
    )


@dataclass
class RepoAddOptions:
    """Options to control 'argocd repo add' invocation."""

    repo_type: str = "git"
    enable_oci: bool = False
    description: str | None = None
    name: str | None = None


def _build_repo_add_args(
    *, repo_url: str, username: str, password: str, options: RepoAddOptions
) -> list[str]:
    args = [
        "argocd",
        "repo",
        "add",
        repo_url,
        "--username",
        username,
        "--password",
        password,
    ]
    if options.repo_type:
        args.extend(["--type", options.repo_type])
    if options.enable_oci:
        args.append("--enable-oci")
    # For Helm (incl. OCI) repos, argocd requires a --name
    if options.repo_type == "helm":
        repo_name = options.name or _derive_repo_name(repo_url)
        if repo_name:
            args.extend(["--name", repo_name])
    # --description is not supported by many argocd CLI versions; omit for compatibility
    return args


def _derive_repo_name(repo_url: str) -> str:
    """Derive a short name from a repo URL like 'registry-1.docker.io/bitnamicharts'."""
    parts = repo_url.rstrip("/").split("/")
    return parts[-1] if parts else repo_url


def _get_initial_admin_password(namespace: str) -> str:
    # base64-encoded password from secret
    jsonpath = "jsonpath={.data.password}"
    data = run(
        [
            "kubectl",
            "-n",
            namespace,
            "get",
            "secret",
            "argocd-initial-admin-secret",
            "-o",
            jsonpath,
        ]
    )
    return base64.b64decode(data.strip()).decode("utf-8")


def to_state(obj: dict[str, Any]) -> AppState:
    """Convert ArgoCD app JSON object into an AppState instance."""
    name = _get_name(obj)
    namespace = _get_namespace(obj)
    health = _get_health(obj)
    sync = _get_sync(obj)
    revision = _dig(obj, ["status", "sync", "revision"]) or None
    return AppState(
        name=str(name),
        namespace=str(namespace),
        health=str(health),  # type: ignore[arg-type]
        sync=str(sync),  # type: ignore[arg-type]
        revision=str(revision) if revision is not None else None,
    )


def _dig(obj: Any, path: list[str]) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _build_create_args(spec: AppSpec) -> list[str]:
    args: list[str] = [
        "argocd",
        "app",
        "create",
        spec.name,
        "--repo",
        spec.repo,
        "--path",
        spec.path,
        "--dest-server",
        "https://kubernetes.default.svc",
        "--dest-namespace",
        spec.namespace,
        "--project",
        spec.project,
    ]
    if spec.type == "helm":
        # ArgoCD expects --values and optionally --release-name for Helm apps;
        # it does not support a standalone --helm flag.
        for v in spec.helm_values:
            args.extend(["--values", v])
    return args


def _build_update_args(spec: AppSpec) -> list[str]:
    args: list[str] = [
        "argocd",
        "app",
        "set",
        spec.name,
        "--repo",
        spec.repo,
        "--path",
        spec.path,
        "--dest-server",
        "https://kubernetes.default.svc",
        "--dest-namespace",
        spec.namespace,
        "--project",
        spec.project,
    ]
    if spec.type == "helm":
        # For Helm apps, keep --values; do not add unsupported --helm flag
        for v in spec.helm_values:
            args.extend(["--values", v])
    return args


def _run_create_or_update(
    client: ArgoClient, args: list[str], spec: AppSpec, updater: Any
) -> None:
    try:
        client.run_with_auth(args)
    except ProcessError as e:
        if "already exists" in (e.stderr or ""):
            updater(spec)
        else:
            raise


def _apply_sync_policy_if_auto(client: ArgoClient, spec: AppSpec) -> None:
    if spec.sync_policy == "auto":
        client.run_with_auth(["argocd", "app", "set", spec.name, "--sync-policy", "auto"])


def _get_name(obj: dict[str, Any]) -> str:
    return str(_dig(obj, ["metadata", "name"]) or obj.get("name", ""))


def _get_namespace(obj: dict[str, Any]) -> str:
    return str(
        _dig(obj, ["spec", "destination", "namespace"]) or obj.get("namespace", "default")
    )


def _get_health(obj: dict[str, Any]) -> str:
    return str(_dig(obj, ["status", "health", "status"]) or "Unknown")


def _get_sync(obj: dict[str, Any]) -> str:
    return str(_dig(obj, ["status", "sync", "status"]) or "Unknown")


def _candidate_servers(preferred: str) -> list[str]:
    """Return candidate ArgoCD server hosts to try for login.

    Includes the preferred value, common local endpoints, and de-duplicates while
    preserving order.
    """
    candidates = [
        preferred,
        "argocd.localtest.me",
        "localhost:8080",
        "127.0.0.1:8080",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for s in candidates:
        if s and s not in seen:
            ordered.append(s)
            seen.add(s)
    return ordered


def _with_server(args: list[str], server: str, *, insecure: bool) -> list[str]:
    """Append --server and --insecure to argocd commands if not present."""
    if not args or args[0] != "argocd":
        return args
    if _is_login_cmd(args):
        return _ensure_insecure_for_login(args, insecure=insecure)
    return _append_server_and_insecure(args, server, insecure=insecure)


def _is_login_cmd(args: list[str]) -> bool:
    """Return True if command is 'argocd login ...'."""
    return len(args) >= LOGIN_SUBCMD_MIN_ARGS and args[1] == "login"


def _ensure_insecure_for_login(args: list[str], *, insecure: bool) -> list[str]:
    """For login command, only ensure --insecure if requested."""
    if insecure and "--insecure" not in args:
        return [*args, "--insecure"]
    return args


def _append_server_and_insecure(args: list[str], server: str, *, insecure: bool) -> list[str]:
    """Append --server <server> and --insecure flags if missing."""
    new_args = list(args)
    if "--server" not in new_args and "-s" not in new_args:
        new_args.extend(["--server", server])
    if insecure and "--insecure" not in new_args:
        new_args.append("--insecure")
    return new_args


def _find_server_with_valid_session(candidates: list[str]) -> str | None:
    """Return the first server that has a valid argocd CLI session, else None."""
    for server in candidates:
        try:
            run(
                ["argocd", "--server", server, "account", "get-user-info", "-o", "json"],
                timeout=10,
            )
        except ProcessError:
            pass
        else:
            return server
    return None


def _logout_stale_session() -> None:
    """Attempt to logout any existing session; ignore failures."""
    with contextlib.suppress(ProcessError):
        logger.info("🚪 Logging out any stale ArgoCD session...")
        run(["argocd", "logout", "--yes"], timeout=5)


def _login_first_success(
    candidates: list[str], password: str, *, insecure: bool
) -> str | None:
    """Try logging into each server, returning the first that succeeds."""
    for server in candidates:
        logger.info("🔐 Attempting ArgoCD login at '%s'", server)
        base_args = [
            "argocd",
            "login",
            server,
            "--username",
            "admin",
            "--password",
            password,
        ]
        if insecure:
            base_args.append("--insecure")

        try:
            run(base_args, timeout=20)
        except ProcessError:
            args2 = [*base_args, "--grpc-web"]
            logger.info("🌐 Retrying login to '%s' with --grpc-web", server)
            try:
                run(args2, timeout=20)
            except ProcessError:
                logger.info("❌ Login failed for '%s'", server)
            else:
                return server
        else:
            return server
    return None
