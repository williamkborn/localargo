# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
from __future__ import annotations

#
# SPDX-License-Identifier: MIT
import base64
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from localargo.logging import logger

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
    name: str, namespace: str, from_literal: tuple[str, ...], from_file: tuple[str, ...], *, dry_run: bool
) -> None:
    """Create a secret from literals or files."""
    data = {}

    # Process literal values
    for literal in from_literal:
        if "=" not in literal:
            logger.info(f"❌ Invalid literal format: {literal} (expected key=value)")
            return
        key, value = literal.split("=", 1)
        data[key] = base64.b64encode(value.encode()).decode()

    # Process file values
    for file_pair in from_file:
        if "=" not in file_pair:
            logger.info(f"❌ Invalid file format: {file_pair} (expected key=file)")
            return
        key, file_path = file_pair.split("=", 1)

        if not Path(file_path).exists():
            logger.info(f"❌ File not found: {file_path}")
            return

        with open(file_path, "rb") as f:
            data[key] = base64.b64encode(f.read()).decode()

    if not data:
        logger.error("❌ No data provided. Use --from-literal or --from-file")
        return

    # Create the secret YAML
    secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: {name}
  namespace: {namespace}
type: Opaque
data:
"""

    for key, value in data.items():
        secret_yaml += f"  {key}: {value}\n"

    if dry_run:
        logger.info("--- DRY RUN ---")
        logger.info(secret_yaml)
        return

    # Write to temp file and apply
    temp_fd, temp_path = tempfile.mkstemp(suffix=".yaml")
    temp_file = Path(temp_path)
    temp_file.write_text(secret_yaml)

    try:
        kubectl_path = shutil.which("kubectl")
        if kubectl_path is None:
            msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
            raise RuntimeError(msg)
        subprocess.run([kubectl_path, "apply", "-f", temp_file], check=True)
        logger.info(f"✅ Secret '{name}' created in namespace '{namespace}'")
    except subprocess.CalledProcessError as e:
        logger.info(f"❌ Error creating secret: {e}")
    finally:
        temp_file.unlink(missing_ok=True)


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def get(name: str, namespace: str) -> None:
    """Get and decode secret values."""
    try:
        # Get secret data
        kubectl_path = shutil.which("kubectl")
        if kubectl_path is None:
            msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
            raise RuntimeError(msg)
        result = subprocess.run(
            [kubectl_path, "get", "secret", name, "-n", namespace, "-o", "jsonpath={.data}"],
            capture_output=True,
            text=True,
            check=True,
        )

        if not result.stdout.strip():
            logger.info(f"❌ Secret '{name}' not found or has no data")
            return

        # Parse and decode the data
        import json

        data = json.loads(result.stdout)

        logger.info(f"Secret: {name} (namespace: {namespace})")
        logger.info("-" * 40)

        for key, encoded_value in data.items():
            try:
                decoded = base64.b64decode(encoded_value).decode("utf-8")
                # Mask sensitive data
                if len(decoded) > MAX_SECRET_DISPLAY_LENGTH:
                    decoded = decoded[:MAX_SECRET_DISPLAY_LENGTH] + "..."
                logger.info(f"{key}: {decoded}")
            except (ValueError, UnicodeDecodeError):
                logger.info(f"{key}: <binary data or decode error>")

    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error getting secret: {e}",
        )


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
@click.option("--key", "-k", required=True, help="Secret key to update")
@click.option("--value", "-v", help="New value")
@click.option("--from-file", help="File containing new value")
def update(name: str, namespace: str, key: str, value: str | None, from_file: str | None) -> None:
    """Update a secret key."""
    if not value and not from_file:
        logger.error(
            "❌ Must provide --value or --from-file",
        )
        return

    if value and from_file:
        logger.error(
            "❌ Cannot specify both --value and --from-file",
        )
        return

    try:
        # Read current secret
        kubectl_path = shutil.which("kubectl")
        if kubectl_path is None:
            msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
            raise RuntimeError(msg)
        result = subprocess.run(
            [kubectl_path, "get", "secret", name, "-n", namespace, "-o", "yaml"],
            capture_output=True,
            text=True,
            check=True,
        )

        import yaml as yaml_lib

        secret = yaml_lib.safe_load(result.stdout)

        # Update the key
        if from_file:
            if not Path(from_file).exists():
                logger.info(
                    f"❌ File not found: {from_file}",
                )
                return
            with open(from_file, "rb") as f:
                encoded_value = base64.b64encode(f.read()).decode()
        else:
            if value is None:
                msg = "Value cannot be None when not reading from file"
                raise ValueError(msg)  # noqa: TRY301
            encoded_value = base64.b64encode(value.encode()).decode()

        if "data" not in secret:
            secret["data"] = {}
        secret["data"][key] = encoded_value

        # Write back to temp file and apply
        temp_fd, temp_path = tempfile.mkstemp(suffix=".yaml")
        temp_file = Path(temp_path)
        temp_file.write_text(yaml_lib.dump(secret))

        kubectl_path = shutil.which("kubectl")
        if kubectl_path is None:
            msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
            raise RuntimeError(msg)
        subprocess.run([kubectl_path, "apply", "-f", temp_file], check=True)
        logger.info(f"✅ Secret '{name}' updated (key: {key})")

    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error updating secret: {e}",
        )
    except (OSError, ValueError) as e:
        logger.info(
            f"❌ Error: {e}",
        )
    finally:
        if "temp_file" in locals():
            temp_file.unlink(missing_ok=True)


@secrets.command()
@click.argument("name")
@click.option("--namespace", "-n", default="default", help="Namespace")
def delete(name: str, namespace: str) -> None:
    """Delete a secret."""
    if click.confirm(f"Delete secret '{name}' from namespace '{namespace}'?"):
        try:
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                raise RuntimeError(msg)
            subprocess.run([kubectl_path, "delete", "secret", name, "-n", namespace], check=True)
            logger.info(f"✅ Secret '{name}' deleted")
        except subprocess.CalledProcessError as e:
            logger.info(
                f"❌ Error deleting secret: {e}",
            )
