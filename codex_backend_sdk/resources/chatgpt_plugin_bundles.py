"""Safe download and extraction of backend-issued remote plugin bundles."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import shutil
import stat
import tarfile
import tempfile
from typing import Any, Literal, TYPE_CHECKING
from urllib.parse import urlparse
import zipfile

import requests

if TYPE_CHECKING:
    from .._client import CodexClient

PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES = 512 * 1024 * 1024


class ChatGPTPluginBundles:
    """Download remote plugin and skill bundles without forwarding OAuth."""

    def __init__(self, client: CodexClient, plugins: Any) -> None:
        self._client = client
        self._plugins = plugins

    def download_plugin(
        self,
        plugin_id: str,
        *,
        response_format: Literal["bytes", "bytes_io", "file"] = "bytes",
        output_path: str | Path | None = None,
        max_bytes: int = PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
    ) -> bytes | BytesIO | Path:
        detail = self._plugins.retrieve(plugin_id, include_download_urls=True)
        release = detail.get("release")
        url = release.get("bundle_download_url") if isinstance(release, dict) else None
        return self._download(
            url,
            response_format=response_format,
            output_path=output_path,
            max_bytes=max_bytes,
        )

    def download_curated(
        self,
        *,
        response_format: Literal["bytes", "bytes_io", "file"] = "bytes",
        output_path: str | Path | None = None,
        max_bytes: int = PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
    ) -> bytes | BytesIO | Path:
        """Download the signed curated-plugin backup archive without OAuth headers."""
        export = self._plugins.curated_export()
        return self._download(
            export.get("download_url"),
            response_format=response_format,
            output_path=output_path,
            max_bytes=max_bytes,
        )

    def download_skill(
        self,
        plugin_id: str,
        skill_name: str,
        *,
        response_format: Literal["bytes", "bytes_io", "file"] = "bytes",
        output_path: str | Path | None = None,
        max_bytes: int = PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
    ) -> bytes | BytesIO | Path:
        detail = self._plugins.skill(plugin_id, skill_name)
        return self._download(
            detail.get("skill_bundle_download_url"),
            response_format=response_format,
            output_path=output_path,
            max_bytes=max_bytes,
        )

    def extract_plugin(
        self,
        plugin_id: str,
        destination: str | Path,
        *,
        max_download_bytes: int = PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
        max_extracted_bytes: int = PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES,
    ) -> Path:
        detail = self._plugins.retrieve(plugin_id, include_download_urls=True)
        release = detail.get("release")
        url = release.get("bundle_download_url") if isinstance(release, dict) else None
        content = self._download_bytes(url, max_bytes=max_download_bytes)
        expected_name = detail.get("name")
        if not isinstance(expected_name, str) or not expected_name:
            raise RuntimeError("Remote plugin detail is missing its name.")
        return _extract_bundle(
            content,
            Path(destination),
            expected_name=expected_name,
            max_extracted_bytes=max_extracted_bytes,
        )

    def extract_curated(
        self,
        destination: str | Path,
        *,
        max_download_bytes: int = PLUGIN_BUNDLE_MAX_DOWNLOAD_BYTES,
        max_extracted_bytes: int = PLUGIN_BUNDLE_MAX_EXTRACTED_BYTES,
    ) -> Path:
        """Materialize the curated export atomically after validating its layout."""
        export = self._plugins.curated_export()
        content = self._download_bytes(
            export.get("download_url"), max_bytes=max_download_bytes
        )
        return _extract_curated_archive(
            content,
            Path(destination),
            max_extracted_bytes=max_extracted_bytes,
        )

    def _download(
        self,
        url: Any,
        *,
        response_format: str,
        output_path: str | Path | None,
        max_bytes: int,
    ) -> bytes | BytesIO | Path:
        if response_format not in {"bytes", "bytes_io", "file"}:
            raise ValueError(f"Unsupported `response_format`: {response_format!r}")
        if response_format == "file" and output_path is None:
            raise ValueError("`output_path` is required when `response_format='file'`.")
        if response_format != "file" and output_path is not None:
            raise ValueError("`output_path` is only valid when `response_format='file'.")
        content = self._download_bytes(url, max_bytes=max_bytes)
        if response_format == "bytes_io":
            return BytesIO(content)
        if response_format == "file":
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return path
        return content

    def _download_bytes(self, url: Any, *, max_bytes: int) -> bytes:
        if not isinstance(url, str) or not url:
            raise RuntimeError("Remote bundle detail is missing its download URL.")
        if max_bytes < 1:
            raise ValueError("Expected `max_bytes` to be positive.")
        _require_https(url, "bundle download URL")
        response = requests.get(
            url,
            stream=True,
            timeout=self._client._timeout,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            _require_https(response.url, "final bundle download URL")
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    announced = int(length)
                except ValueError as exc:
                    raise RuntimeError("Bundle response has invalid Content-Length.") from exc
                if announced > max_bytes:
                    raise ValueError(f"Remote bundle exceeds {max_bytes} download bytes.")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                if len(content) + len(chunk) > max_bytes:
                    raise ValueError(f"Remote bundle exceeds {max_bytes} download bytes.")
                content.extend(chunk)
            return bytes(content)
        finally:
            response.close()


def _extract_bundle(
    content: bytes,
    destination: Path,
    *,
    expected_name: str,
    max_extracted_bytes: int,
) -> Path:
    if destination.exists():
        raise ValueError(f"Plugin extraction destination already exists: `{destination}`")
    if max_extracted_bytes < 1:
        raise ValueError("Expected `max_extracted_bytes` to be positive.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="remote-plugin-", dir=destination.parent))
    try:
        total = 0
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                if member.issym() or member.islnk():
                    raise ValueError(f"Plugin bundle entry `{member.name}` is a link.")
                if not (member.isdir() or member.isfile()):
                    raise ValueError(
                        f"Plugin bundle entry `{member.name}` has unsupported type."
                    )
                target = _safe_output_path(staging, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += member.size
                if total > max_extracted_bytes:
                    raise ValueError(
                        f"Plugin bundle exceeds {max_extracted_bytes} extracted bytes."
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"Plugin bundle entry `{member.name}` has no data.")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        manifest = next(
            (
                candidate
                for candidate in (
                    staging / ".codex-plugin/plugin.json",
                    staging / "plugin.json",
                )
                if candidate.is_file()
            ),
            None,
        )
        if manifest is None:
            raise ValueError("Remote plugin bundle has no standard plugin manifest.")
        try:
            manifest_payload = json.loads(manifest.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Remote plugin manifest is invalid JSON.") from exc
        if not isinstance(manifest_payload, dict):
            raise ValueError("Remote plugin manifest is not a JSON object.")
        if manifest_payload.get("name") != expected_name:
            raise ValueError("Remote plugin manifest name does not match plugin detail.")
        staging.rename(destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _extract_curated_archive(
    content: bytes,
    destination: Path,
    *,
    max_extracted_bytes: int,
) -> Path:
    if destination.exists():
        raise ValueError(f"Curated extraction destination already exists: `{destination}`")
    if max_extracted_bytes < 1:
        raise ValueError("Expected `max_extracted_bytes` to be positive.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="curated-plugins-", dir=destination.parent))
    try:
        total = 0
        with zipfile.ZipFile(BytesIO(content)) as archive:
            for entry in archive.infolist():
                relative = _curated_relative_path(entry.filename)
                if relative is None:
                    continue
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError(
                        f"Curated plugin archive entry `{entry.filename}` has unsupported type."
                    )
                target = _safe_output_path(staging, relative.as_posix())
                if entry.is_dir() or kind == stat.S_IFDIR:
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                total += entry.file_size
                if total > max_extracted_bytes:
                    raise ValueError(
                        f"Curated plugin archive exceeds {max_extracted_bytes} extracted bytes."
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

        manifest = staging / ".agents/plugins/marketplace.json"
        if not manifest.is_file():
            raise ValueError("Curated plugin archive has no marketplace manifest.")
        try:
            payload = json.loads(manifest.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Curated plugin marketplace manifest is invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Curated plugin marketplace manifest is not a JSON object.")
        staging.rename(destination)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _curated_relative_path(name: str) -> Path | None:
    path = Path(name)
    if path.is_absolute() or "\\" in name:
        raise ValueError(f"Curated plugin archive entry `{name}` has an unsafe path.")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Curated plugin archive entry `{name}` has an unsafe path.")
    # Both the GitHub zipball and the backend backup wrap the checkout in one
    # generated top-level directory. Codex deliberately strips that component.
    relative_parts = parts[1:]
    if not relative_parts:
        return None
    return Path(*relative_parts)


def _safe_output_path(root: Path, name: str) -> Path:
    parts = Path(name).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Plugin bundle entry `{name}` has an unsafe path.")
    candidate = root.joinpath(*parts)
    if not candidate.is_relative_to(root):
        raise ValueError(f"Plugin bundle entry `{name}` escapes extraction root.")
    return candidate


def _require_https(url: str, label: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"Expected {label} to use HTTPS.")
