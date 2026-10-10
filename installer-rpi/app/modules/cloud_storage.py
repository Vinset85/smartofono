"""Cloud storage delle clip / snapshots — scaffold S3-compatible.

Supporta qualsiasi provider con API S3 (AWS S3, Backblaze B2, Wasabi,
MinIO self-hosted). Configurazione:

    cloud_storage:
      enabled: false
      provider: s3                      # solo s3 per ora
      bucket: videocitofono-clips
      prefix: rpi5/                     # opzionale
      region: us-east-1
      endpoint_url: ""                  # vuoto = AWS, altrimenti es. https://s3.eu-west-1.wasabisys.com
      access_key: "..."
      secret_key: "..."
      retention_days: 30

L'upload e' asincrono (thread). Se boto3 non e' installato, il modulo
e' no-op silenzioso. Per attivare:
    pip install boto3
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional


LOG = logging.getLogger(__name__)


class CloudUploader:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.bucket = str(cfg.get("bucket", ""))
        self.prefix = str(cfg.get("prefix", "")).lstrip("/")
        self.region = str(cfg.get("region", "us-east-1"))
        self.endpoint_url = str(cfg.get("endpoint_url", "")) or None
        self.access_key = str(cfg.get("access_key", ""))
        self.secret_key = str(cfg.get("secret_key", ""))
        self.retention_days = int(cfg.get("retention_days", 30))
        self._client = None
        self._available: Optional[bool] = None

    def _ensure(self) -> bool:
        if not self.enabled or not self.bucket:
            return False
        if self._available is not None:
            return self._available
        try:
            import boto3  # type: ignore
            self._client = boto3.client(
                "s3",
                region_name=self.region or None,
                endpoint_url=self.endpoint_url or None,
                aws_access_key_id=self.access_key or None,
                aws_secret_access_key=self.secret_key or None,
            )
            self._available = True
            LOG.info("CloudUploader pronto (bucket=%s endpoint=%s)",
                     self.bucket, self.endpoint_url or "AWS-default")
        except Exception as e:
            LOG.warning("CloudUploader non disponibile: %s", e)
            self._available = False
        return self._available

    def is_available(self) -> bool:
        return self._ensure()

    def _make_key(self, local_path: str) -> str:
        ts = time.strftime("%Y/%m/%d", time.localtime())
        return f"{self.prefix}{ts}/{os.path.basename(local_path)}"

    def upload_async(self, local_path: str, key: Optional[str] = None,
                     delete_after: bool = False,
                     content_type: Optional[str] = None) -> bool:
        if not self._ensure() or not os.path.exists(local_path):
            return False
        threading.Thread(
            target=self._upload_blocking,
            args=(local_path, key, delete_after, content_type),
            name="cloud-upload",
            daemon=True,
        ).start()
        return True

    def _upload_blocking(self, local_path: str, key: Optional[str],
                         delete_after: bool,
                         content_type: Optional[str]) -> None:
        try:
            kk = key or self._make_key(local_path)
            extra = {}
            if content_type:
                extra["ContentType"] = content_type
            if self.retention_days > 0:
                exp = int(time.time() + self.retention_days * 86400)
                extra["Metadata"] = {"expire-ts": str(exp)}
            self._client.upload_file(local_path, self.bucket, kk, ExtraArgs=extra)
            LOG.info("cloud upload OK: s3://%s/%s", self.bucket, kk)
            if delete_after:
                try:
                    os.remove(local_path)
                except Exception:
                    pass
        except Exception as e:
            LOG.warning("cloud upload err: %s", e)
