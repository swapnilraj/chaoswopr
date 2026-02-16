"""S3 storage client for chaoswopr audit logs and experiment artifacts.

Provides append-only storage for audit logs with object lock support
for tamper-evident compliance requirements (ERC-8004-style).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig


def get_s3_config() -> dict[str, str]:
    """Get S3 configuration from environment variables.

    Returns:
        Dictionary with S3 configuration.
    """
    return {
        "endpoint_url": os.environ.get("CHAOSWOPR_S3_ENDPOINT", ""),
        "bucket_audit": os.environ.get("CHAOSWOPR_S3_AUDIT_BUCKET", "chaoswopr-audit-logs"),
        "bucket_artifacts": os.environ.get(
            "CHAOSWOPR_S3_ARTIFACTS_BUCKET", "chaoswopr-artifacts"
        ),
        "region": os.environ.get("CHAOSWOPR_S3_REGION", "us-east-1"),
    }


class S3Storage:
    """S3 storage client for audit logs and experiment artifacts.

    Supports append-only audit log storage with object lock for tamper evidence.
    """

    def __init__(
        self,
        client: Any | None = None,
        audit_bucket: str | None = None,
        artifacts_bucket: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """Initialize the S3 storage client.

        Args:
            client: Pre-configured boto3 S3 client (for testing).
            audit_bucket: Bucket name for audit logs.
            artifacts_bucket: Bucket name for experiment artifacts.
            endpoint_url: Custom S3 endpoint (for MinIO, localstack).
        """
        config = get_s3_config()
        self._audit_bucket = audit_bucket or config["bucket_audit"]
        self._artifacts_bucket = artifacts_bucket or config["bucket_artifacts"]

        if client:
            self._client = client
        else:
            endpoint = endpoint_url or config["endpoint_url"]
            kwargs: dict[str, Any] = {
                "region_name": config["region"],
                "config": BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
            }
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            self._client = boto3.client("s3", **kwargs)

    @property
    def client(self) -> Any:
        """Get the boto3 S3 client."""
        return self._client

    def health_check(self) -> bool:
        """Check S3 connectivity by listing buckets.

        Returns:
            True if S3 is reachable.
        """
        try:
            self._client.list_buckets()
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------
    # Audit Log operations
    # -------------------------------------------------------------------

    def write_audit_log(
        self,
        entry: dict[str, Any],
        experiment_id: str | None = None,
    ) -> str:
        """Write an audit log entry to S3.

        The entry is stored as a JSON object with a key based on
        timestamp and trace_id for uniqueness and chronological ordering.

        Args:
            entry: Audit log entry dictionary.
            experiment_id: Optional experiment ID for key partitioning.

        Returns:
            The S3 object key where the entry was stored.
        """
        timestamp = entry.get("timestamp", datetime.now(timezone.utc).isoformat())
        trace_id = entry.get("trace_id", "unknown")

        # Build hierarchical key: year/month/day/experiment_id/timestamp_trace_id.json
        dt = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        prefix = f"audit/{dt.year}/{dt.month:02d}/{dt.day:02d}"
        if experiment_id:
            prefix = f"{prefix}/{experiment_id}"
        key = f"{prefix}/{dt.strftime('%H%M%S')}_{trace_id}.json"

        self._client.put_object(
            Bucket=self._audit_bucket,
            Key=key,
            Body=json.dumps(entry, default=str).encode("utf-8"),
            ContentType="application/json",
        )

        return key

    def write_audit_logs_batch(
        self,
        entries: list[dict[str, Any]],
        experiment_id: str | None = None,
    ) -> list[str]:
        """Write multiple audit log entries to S3.

        Args:
            entries: List of audit log entry dictionaries.
            experiment_id: Optional experiment ID for key partitioning.

        Returns:
            List of S3 object keys.
        """
        keys = []
        for entry in entries:
            key = self.write_audit_log(entry, experiment_id)
            keys.append(key)
        return keys

    def read_audit_log(self, key: str) -> dict[str, Any]:
        """Read an audit log entry from S3.

        Args:
            key: S3 object key.

        Returns:
            The audit log entry as a dictionary.
        """
        response = self._client.get_object(Bucket=self._audit_bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)

    def list_audit_logs(
        self,
        prefix: str = "audit/",
        max_keys: int = 1000,
    ) -> list[str]:
        """List audit log keys in S3.

        Args:
            prefix: Key prefix to filter by.
            max_keys: Maximum number of keys to return.

        Returns:
            List of S3 object keys.
        """
        response = self._client.list_objects_v2(
            Bucket=self._audit_bucket,
            Prefix=prefix,
            MaxKeys=max_keys,
        )
        return [obj["Key"] for obj in response.get("Contents", [])]

    # -------------------------------------------------------------------
    # Experiment Artifact operations
    # -------------------------------------------------------------------

    def write_artifact(
        self,
        experiment_id: str,
        artifact_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Write an experiment artifact to S3.

        Args:
            experiment_id: The experiment UUID.
            artifact_name: Name of the artifact.
            data: Artifact content as bytes.
            content_type: MIME type of the artifact.

        Returns:
            The S3 object key.
        """
        key = f"artifacts/{experiment_id}/{artifact_name}"
        self._client.put_object(
            Bucket=self._artifacts_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def read_artifact(self, experiment_id: str, artifact_name: str) -> bytes:
        """Read an experiment artifact from S3.

        Args:
            experiment_id: The experiment UUID.
            artifact_name: Name of the artifact.

        Returns:
            Artifact content as bytes.
        """
        key = f"artifacts/{experiment_id}/{artifact_name}"
        response = self._client.get_object(Bucket=self._artifacts_bucket, Key=key)
        return response["Body"].read()

    def list_artifacts(self, experiment_id: str) -> list[str]:
        """List artifacts for an experiment.

        Args:
            experiment_id: The experiment UUID.

        Returns:
            List of artifact names.
        """
        prefix = f"artifacts/{experiment_id}/"
        response = self._client.list_objects_v2(
            Bucket=self._artifacts_bucket,
            Prefix=prefix,
        )
        return [
            obj["Key"].replace(prefix, "") for obj in response.get("Contents", [])
        ]
