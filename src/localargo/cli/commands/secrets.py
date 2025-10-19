# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Secrets management for ArgoCD applications.

This module provides commands for managing Kubernetes secrets used by ArgoCD applications.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

import click
import yaml

from localargo.logging import logger
from localargo.utils.cli import run_subprocess

# Constants
MAX_SECRET_DISPLAY_LENGTH = 50


@click.group()
def secrets() -> None:
    """Manage secrets for local ArgoCD development."""


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
@click.option("--from-literal", "-l", multiple=True, help="Key=value pairs")
@click.option("--from-file", "-f", multiple=True, help="Key=file pairs")
@click.option("--dry-run", is_flag=True, help="Show what would be created")
def create(
    name: str,
    namespace: str,
    from_literal: tuple[str, ...],
    from_file: tuple[str, ...],
    *,
    dry_run: bool,
) -> None:
    """Create a secret from literals or files."""
    secret_data = _build_secret_data(from_literal, from_file)
    if not secret_data:
        return

    secret_yaml = _generate_secret_yaml(name, namespace, secret_data)

    if dry_run:
        logger.info("--- DRY RUN ---")
        logger.info(secret_yaml)
        return

    # Apply the secret
    _apply_secret_yaml(secret_yaml, name, namespace)


def _build_secret_data(
    from_literal: tuple[str, ...], from_file: tuple[str, ...]
) -> dict[str, str]:
    """Build secret data from literals and files."""
    data: dict[str, str] = {}

    # Process literal values
    if not _accumulate_literal_values(from_literal, data):
        return {}

    # Process file values
    if not _accumulate_file_values(from_file, data):
        return {}

    if not data:
        logger.error("❌ No data provided. Use --from-literal or --from-file")

    return data


def _accumulate_literal_values(literals: tuple[str, ...], data: dict[str, str]) -> bool:
    """Parse and add literal key=value pairs into data. Return False on error."""
    for literal in literals:
        if "=" not in literal:
            logger.error("❌ Invalid literal format: %s (expected key=value)", literal)
            return False
        key, val = literal.split("=", 1)
        data[key] = base64.b64encode(val.encode()).decode()
    return True


def _accumulate_file_values(file_specs: tuple[str, ...], data: dict[str, str]) -> bool:
    """Parse and add file-based key=file pairs into data. Return False on error."""
    for file_spec in file_specs:
        if "=" not in file_spec:
            logger.error("❌ Invalid file format: %s (expected key=file)", file_spec)
            return False
        key, file_path = file_spec.split("=", 1)

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error("❌ File not found: %s", file_path)
            return False

        with open(file_path_obj, "rb") as file_handle:
            data[key] = base64.b64encode(file_handle.read()).decode()
    return True


def _generate_secret_yaml(name: str, namespace: str, data: dict[str, str]) -> str:
    """Generate YAML for the secret."""
    yaml_lines = [
        f"""apiVersion: v1
kind: Secret
metadata:
  name: {name}
  namespace: {namespace}
type: Opaque
data:
"""
    ]

    for key, val in data.items():
        yaml_lines.append(f"  {key}: {val}\n")

    return "".join(yaml_lines)


def _apply_secret_yaml(secret_yaml: str, name: str, namespace: str) -> None:
    """Apply the secret YAML to the cluster."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp_file:
        tmp_file.write(secret_yaml)
        tmp_path = tmp_file.name

    temp_file_path = Path(tmp_path)

    try:
        run_subprocess(["kubectl", "apply", "-f", str(temp_file_path)])
        logger.info("✅ Secret '%s' created in namespace '%s'", name, namespace)
    except subprocess.CalledProcessError as err:
        logger.info("❌ Error creating secret: %s", err)
    finally:
        temp_file_path.unlink(missing_ok=True)


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def get(name: str, namespace: str) -> None:
    """Get and decode secret values."""
    try:
        # Get secret data
        result = run_subprocess(
            ["kubectl", "get", "secret", name, "-n", namespace, "-o", "jsonpath={.data}"]
        )

        if not result.stdout.strip():
            logger.info("❌ Secret '%s' not found or has no data", name)
            return

        # Parse and decode the data
        data = json.loads(result.stdout)

        logger.info("Secret: %s (namespace: %s)", name, namespace)
        logger.info("-" * 40)

        for key, encoded_value in data.items():
            try:
                decoded = base64.b64decode(encoded_value).decode("utf-8")
                # Mask sensitive data
                if len(decoded) > MAX_SECRET_DISPLAY_LENGTH:
                    decoded = decoded[:MAX_SECRET_DISPLAY_LENGTH] + "..."
                logger.info("%s: %s", key, decoded)
            except (ValueError, UnicodeDecodeError):
                logger.info("%s: <binary data or decode error>", key)

    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error getting secret: %s",
            e,
        )


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
@click.option("--key", "-k", required=True, help="Secret key to update")
@click.option("--value", "-v", help="New value")
@click.option("--from-file", help="File containing new value")
def update(
    name: str, namespace: str, key: str, value: str | None, from_file: str | None
) -> None:
    """Update a secret key."""
    if not _validate_update_inputs(value, from_file):
        return

    try:
        secret = _read_current_secret(name, namespace)
        encoded_value = _get_encoded_value(value, from_file)

        _update_secret_data(secret, key, encoded_value)
        _apply_updated_secret(secret, name, key)

    except subprocess.CalledProcessError as e:
        logger.error("❌ Updating secret failed with return code %s", e.returncode)
        if e.stderr:
            logger.error("Error details: %s", e.stderr.strip())
        raise
    except (OSError, ValueError) as e:
        logger.error("❌ Error updating secret: %s", e)
        raise


def _validate_update_inputs(value: str | None, from_file: str | None) -> bool:
    """Validate update command inputs."""
    if not value and not from_file:
        logger.error("❌ Must provide --value or --from-file")
        return False

    if value and from_file:
        logger.error("❌ Cannot specify both --value and --from-file")
        return False

    return True


def _read_current_secret(name: str, namespace: str) -> dict[str, str | dict[str, str]]:
    """Read the current secret from the cluster."""
    result = run_subprocess(["kubectl", "get", "secret", name, "-n", namespace, "-o", "yaml"])
    secret_data = yaml.safe_load(result.stdout)
    if not isinstance(secret_data, dict):
        msg = f"Expected dict from kubectl output, got {type(secret_data)}"
        raise TypeError(msg)
    return secret_data


def _get_encoded_value(value: str | None, from_file: str | None) -> str:
    """Get the base64 encoded value from either direct value or file."""
    if from_file:
        if not Path(from_file).exists():
            logger.error("❌ File not found: %s", from_file)
            msg = f"File not found: {from_file}"
            raise FileNotFoundError(msg)
        with open(from_file, "rb") as f:
            return base64.b64encode(f.read()).decode()
    else:
        if value is None:
            msg = "Value cannot be None when not reading from file"
            raise ValueError(msg)
        return base64.b64encode(value.encode()).decode()


def _update_secret_data(
    secret: dict[str, str | dict[str, str]], key: str, encoded_value: str
) -> None:
    """Update the secret data with the new key-value pair."""
    if "data" not in secret:
        secret["data"] = {}
    data_section = secret["data"]
    if isinstance(data_section, dict):
        data_section[key] = encoded_value


def _apply_updated_secret(
    secret: dict[str, str | dict[str, str]], name: str, key: str
) -> None:
    """Apply the updated secret to the cluster."""
    temp_file = _write_secret_to_temp_file(secret)
    try:
        run_subprocess(["kubectl", "apply", "-f", str(temp_file)])
        logger.info("✅ Secret '%s' updated (key: %s)", name, key)
    finally:
        temp_file.unlink(missing_ok=True)


def _write_secret_to_temp_file(secret: dict[str, str | dict[str, str]]) -> Path:
    """Write secret to a temporary file and return the path."""
    temp_fd, temp_path = tempfile.mkstemp(suffix=".yaml")
    os.close(temp_fd)  # Close the unused file descriptor
    temp_file = Path(temp_path)
    temp_file.write_text(yaml.dump(secret), encoding="utf-8")
    return temp_file


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def delete(name: str, namespace: str) -> None:
    """Delete a secret."""
    if click.confirm(f"Delete secret '{name}' from namespace '{namespace}'?"):
        try:
            run_subprocess(["kubectl", "delete", "secret", name, "-n", namespace])
            logger.info("✅ Secret '%s' deleted", name)
        except subprocess.CalledProcessError as e:
            logger.info(
                "❌ Error deleting secret: %s",
                e,
            )
