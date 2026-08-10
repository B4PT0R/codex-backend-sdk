"""Workspace plugin publication and sharing contracts from current Codex."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tarfile
from typing import Any, Literal, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from .._client import CodexClient

PLUGIN_ARCHIVE_LIMIT_BYTES = 50 * 1024 * 1024
PLUGIN_ARCHIVE_MIME_TYPE = "application/gzip"


class ChatGPTPluginShares:
    """Explicit workspace-plugin publication and access mutations."""

    def __init__(self, client: CodexClient) -> None:
        self._client = client

    def created(
        self,
        *,
        limit: int = 200,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("Expected `limit` to be positive.")
        payload = self._client._get_chatgpt(
            "/ps/plugins/workspace/created",
            params={
                "limit": limit,
                **({} if page_token is None else {"pageToken": _required(page_token, "page_token")}),
            },
            headers=_headers(),
        )
        _validate_page(payload)
        return payload

    def created_all(self) -> list[dict[str, Any]]:
        plugins: list[dict[str, Any]] = []
        token: str | None = None
        seen: set[str] = set()
        while True:
            page = self.created(page_token=token)
            plugins.extend(page["plugins"])
            next_token = page["pagination"].get("next_page_token")
            if next_token is None:
                return plugins
            if not isinstance(next_token, str) or not next_token:
                raise RuntimeError("Plugin shares returned an invalid next page token.")
            if next_token in seen:
                raise RuntimeError("Plugin shares returned a repeated next page token.")
            seen.add(next_token)
            token = next_token

    def create_upload(
        self,
        *,
        filename: str,
        size_bytes: int,
        plugin_id: str | None = None,
    ) -> dict[str, Any]:
        if size_bytes < 0 or size_bytes > PLUGIN_ARCHIVE_LIMIT_BYTES:
            raise ValueError(
                f"Expected `size_bytes` between 0 and {PLUGIN_ARCHIVE_LIMIT_BYTES}."
            )
        body: dict[str, Any] = {
            "filename": _required(filename, "filename"),
            "mime_type": PLUGIN_ARCHIVE_MIME_TYPE,
            "size_bytes": size_bytes,
        }
        if plugin_id is not None:
            body["plugin_id"] = _required(plugin_id, "plugin_id")
        payload = self._client._request_chatgpt(
            "POST",
            "/public/plugins/workspace/upload-url",
            body=body,
            headers=_headers(),
        ).json()
        if not isinstance(payload, dict):
            raise RuntimeError("Plugin share upload returned an invalid response.")
        for field in ("file_id", "upload_url", "etag"):
            if not isinstance(payload.get(field), str) or not payload[field]:
                raise RuntimeError(f"Plugin share upload is missing `{field}`.")
        return payload

    def finish_upload(
        self,
        *,
        file_id: str,
        etag: str,
        plugin_id: str | None = None,
        discoverability: Literal["LISTED", "UNLISTED", "PRIVATE"] | None = None,
        share_targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "file_id": _required(file_id, "file_id"),
            "etag": _required(etag, "etag"),
        }
        normalized = self._access_policy(discoverability, share_targets)
        body.update(normalized)
        path = "/public/plugins/workspace"
        if plugin_id is not None:
            path += f"/{_path_segment(plugin_id, 'plugin_id')}"
        payload = self._client._request_chatgpt(
            "POST", path, body=body, headers=_headers()
        ).json()
        remote_id = payload.get("plugin_id") if isinstance(payload, dict) else None
        if not isinstance(remote_id, str) or not remote_id:
            raise RuntimeError("Plugin share finalization is missing `plugin_id`.")
        return payload

    def publish_archive(
        self,
        path: str | Path,
        *,
        plugin_id: str | None = None,
        discoverability: Literal["LISTED", "UNLISTED", "PRIVATE"] | None = None,
        share_targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    ) -> dict[str, Any]:
        archive = Path(path)
        if not archive.exists():
            raise FileNotFoundError(f"path `{archive}` does not exist")
        if not archive.is_file():
            raise ValueError(f"path `{archive}` is not a file")
        if archive.stat().st_size > PLUGIN_ARCHIVE_LIMIT_BYTES:
            raise ValueError(
                f"Plugin archive exceeds {PLUGIN_ARCHIVE_LIMIT_BYTES} compressed bytes."
            )
        return self._publish_bytes(
            archive.name,
            archive.read_bytes(),
            plugin_id=plugin_id,
            discoverability=discoverability,
            share_targets=share_targets,
        )

    def publish_directory(
        self,
        path: str | Path,
        *,
        plugin_id: str | None = None,
        discoverability: Literal["LISTED", "UNLISTED", "PRIVATE"] | None = None,
        share_targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    ) -> dict[str, Any]:
        directory = Path(path)
        archive = _pack_plugin_directory(directory)
        return self._publish_bytes(
            f"{directory.name}.tar.gz",
            archive,
            plugin_id=plugin_id,
            discoverability=discoverability,
            share_targets=share_targets,
        )

    def update_targets(
        self,
        plugin_id: str,
        *,
        discoverability: Literal["LISTED", "UNLISTED", "PRIVATE"],
        targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> dict[str, Any]:
        policy = self._access_policy(discoverability, targets)
        payload = self._client._request_chatgpt(
            "PUT",
            f"/ps/plugins/{_path_segment(plugin_id, 'plugin_id')}/shares",
            body={
                "discoverability": policy["discoverability"],
                "targets": policy.get("share_targets", []),
            },
            headers=_headers(),
        ).json()
        if not isinstance(payload, dict) or not isinstance(payload.get("principals"), list):
            raise RuntimeError("Plugin share update returned invalid principals.")
        if payload.get("discoverability") not in {"LISTED", "UNLISTED", "PRIVATE"}:
            raise RuntimeError("Plugin share update returned invalid discoverability.")
        return payload

    def delete(self, plugin_id: str) -> None:
        response = self._client._request_chatgpt(
            "DELETE",
            f"/public/plugins/workspace/{_path_segment(plugin_id, 'plugin_id')}",
            headers=_headers(),
        )
        if response.status_code != 204:
            raise RuntimeError(
                f"Plugin share deletion returned unexpected HTTP {response.status_code}."
            )

    def _publish_bytes(
        self,
        filename: str,
        content: bytes,
        *,
        plugin_id: str | None,
        discoverability: Literal["LISTED", "UNLISTED", "PRIVATE"] | None,
        share_targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    ) -> dict[str, Any]:
        upload = self.create_upload(
            filename=filename, size_bytes=len(content), plugin_id=plugin_id
        )
        response = requests.put(
            upload["upload_url"],
            data=content,
            headers={
                "x-ms-blob-type": "BlockBlob",
                "Content-Type": PLUGIN_ARCHIVE_MIME_TYPE,
            },
            timeout=self._client._timeout,
        )
        response.raise_for_status()
        return self.finish_upload(
            file_id=upload["file_id"],
            etag=upload["etag"],
            plugin_id=plugin_id,
            discoverability=discoverability,
            share_targets=share_targets,
        )

    def _access_policy(
        self,
        discoverability: str | None,
        share_targets: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    ) -> dict[str, Any]:
        if discoverability is not None and discoverability not in {
            "LISTED",
            "UNLISTED",
            "PRIVATE",
        }:
            raise ValueError(f"Unsupported plugin discoverability: {discoverability!r}")
        targets = None if share_targets is None else [_target(item) for item in share_targets]
        if discoverability == "UNLISTED":
            account_id = self._client.account_info().get("account_id")
            if not isinstance(account_id, str) or not account_id:
                raise RuntimeError("Unlisted plugin sharing requires a workspace account ID.")
            targets = [] if targets is None else targets
            if not any(
                item["principal_type"] == "workspace"
                and item["principal_id"] == account_id
                for item in targets
            ):
                targets.append(
                    {
                        "principal_type": "workspace",
                        "principal_id": account_id,
                        "role": "reader",
                    }
                )
        policy: dict[str, Any] = {}
        if discoverability is not None:
            policy["discoverability"] = discoverability
        if targets is not None:
            policy["share_targets"] = targets
        return policy


def _pack_plugin_directory(path: Path) -> bytes:
    if not path.is_dir():
        raise ValueError(f"path `{path}` is not a plugin directory")
    manifest = next(
        (
            candidate
            for candidate in (path / ".codex-plugin/plugin.json", path / "plugin.json")
            if candidate.is_file()
        ),
        None,
    )
    if manifest is None:
        raise ValueError("Plugin directory is missing a plugin manifest.")
    try:
        if not isinstance(json.loads(manifest.read_text()), dict):
            raise ValueError
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Plugin manifest is not a valid JSON object.") from exc

    entries = sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix())
    for entry in entries:
        if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
            raise ValueError(f"Unsupported plugin archive entry: `{entry}`")
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for entry in entries:
            archive.add(
                entry,
                arcname=entry.relative_to(path).as_posix(),
                recursive=False,
            )
    content = buffer.getvalue()
    if len(content) > PLUGIN_ARCHIVE_LIMIT_BYTES:
        raise ValueError(
            f"Plugin archive exceeds {PLUGIN_ARCHIVE_LIMIT_BYTES} compressed bytes."
        )
    return content


def _target(value: dict[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError("Expected each plugin share target to be an object.")
    principal_type = value.get("principal_type")
    role = value.get("role")
    if principal_type not in {"user", "group", "workspace"}:
        raise ValueError(f"Unsupported share principal type: {principal_type!r}")
    if role not in {"reader", "editor"}:
        raise ValueError(f"Unsupported share target role: {role!r}")
    return {
        "principal_type": principal_type,
        "principal_id": _required(value.get("principal_id"), "principal_id"),
        "role": role,
    }


def _headers() -> dict[str, str]:
    return {"OAI-Product-Sku": "codex"}


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected a non-empty string for `{name}`.")
    return value


def _path_segment(value: str, name: str) -> str:
    from urllib.parse import quote

    return quote(_required(value, name), safe="")


def _validate_page(payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("plugins"), list) or not isinstance(
        payload.get("pagination"), dict
    ):
        raise RuntimeError("Plugin shares returned an invalid page.")
