#!/usr/bin/env python3
"""
Sync /data/shared → Marinara (auto-import) + Lumiverse staging.
All three frontends speak standard character cards (PNG chara/ccv3, JSON V1/V2/V3).
Marinara/Lumiverse already translate internally — hub only needs to import new files.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
SHARED = DATA_ROOT / "shared"
STAGING_MARINARA = DATA_ROOT / "marinara" / "storage" / "import-staging"
STAGING_LUMIVERSE = DATA_ROOT / "lumiverse" / "import-staging"
STATE_DIR = DATA_ROOT / ".hub-sync"
STATE_FILE = STATE_DIR / "import-state.json"
MARINARA_PORT = int(os.environ.get("MARINARA_PORT", "7862"))
LUMIVERSE_PORT = int(os.environ.get("LUMIVERSE_PORT", "7861"))
ST_ROOT = DATA_ROOT / "sillytavern"


def log(msg: str) -> None:
    print(f"[sync] {msg}", flush=True)


def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {"characters": {}, "world_info": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"characters": {}, "world_info": {}}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def file_sig(path: Path) -> str:
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def rsync_shared() -> None:
    import subprocess

    pairs = [
        (SHARED / "characters", STAGING_MARINARA / "characters"),
        (SHARED / "characters", STAGING_LUMIVERSE / "characters"),
        (SHARED / "world_info", STAGING_MARINARA / "world_info"),
        (SHARED / "world_info", STAGING_LUMIVERSE / "world_info"),
        (SHARED / "connections", STAGING_MARINARA / "connections"),
        (SHARED / "connections", STAGING_LUMIVERSE / "connections"),
    ]
    for src, dst in pairs:
        src.mkdir(parents=True, exist_ok=True)
        dst.mkdir(parents=True, exist_ok=True)
        delete = "--delete" if src.name in {"characters", "world_info"} else ""
        cmd = ["rsync", "-a"]
        if delete:
            cmd.append(delete)
        cmd.extend([f"{src}/", f"{dst}/"])
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def backend_up(port: int) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, object]:
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"error": raw}
        except json.JSONDecodeError:
            payload = {"error": raw or exc.reason}
        return exc.code, payload


def multipart_batch(url: str, files: list[tuple[str, bytes]]) -> tuple[int, object]:
    boundary = f"hubsync-{uuid4().hex}"
    parts: list[bytes] = []

    for name, content in files:
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'.encode())
        parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
        parts.append(content)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"error": raw}
        except json.JSONDecodeError:
            payload = {"error": raw or exc.reason}
        return exc.code, payload


def import_characters_to_marinara(state: dict) -> int:
    char_dir = SHARED / "characters"
    if not char_dir.is_dir():
        return 0
    if not backend_up(MARINARA_PORT):
        log("marinara not running — skip auto-import (switch to Marinara first)")
        return 0

    pending: list[tuple[str, Path]] = []
    for path in sorted(char_dir.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in {".png", ".json", ".charx"}:
            continue
        rel = str(path.relative_to(SHARED))
        sig = file_sig(path)
        if state["characters"].get(rel) == sig:
            continue
        pending.append((rel, path))

    if not pending:
        return 0

    imported = 0
    batch: list[tuple[str, bytes]] = []
    batch_meta: list[str] = []

    def flush_batch() -> None:
        nonlocal imported, batch, batch_meta
        if not batch:
            return
        url = f"http://127.0.0.1:{MARINARA_PORT}/api/import/st-character/batch"
        status, payload = multipart_batch(url, batch)
        if status >= 400:
            log(f"marinara character batch import failed ({status}): {payload}")
            batch = []
            batch_meta = []
            return
        results = payload.get("results", []) if isinstance(payload, dict) else []
        for rel, result in zip(batch_meta, results):
            if result.get("success"):
                state["characters"][rel] = file_sig(SHARED / rel)
                imported += 1
                log(f"imported character → marinara: {rel}")
            else:
                log(f"marinara import failed for {rel}: {result.get('error', 'unknown')}")
        batch = []
        batch_meta = []

    for rel, path in pending:
        try:
            content = path.read_bytes()
        except OSError as exc:
            log(f"read failed {rel}: {exc}")
            continue
        batch.append((path.name, content))
        batch_meta.append(rel)
        if len(batch) >= 10:
            flush_batch()
    flush_batch()
    return imported


def import_lorebooks_to_marinara(state: dict) -> int:
    world_dir = SHARED / "world_info"
    if not world_dir.is_dir():
        return 0
    if not backend_up(MARINARA_PORT):
        return 0

    imported = 0
    for path in sorted(world_dir.glob("*.json")):
        rel = str(path.relative_to(SHARED))
        sig = file_sig(path)
        if state["world_info"].get(rel) == sig:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log(f"skip lorebook {rel}: {exc}")
            continue
        payload["__filename"] = path.name
        url = f"http://127.0.0.1:{MARINARA_PORT}/api/import/st-lorebook"
        status, result = http_json("POST", url, payload)
        if status < 400 and isinstance(result, dict) and result.get("success", True):
            state["world_info"][rel] = sig
            imported += 1
            log(f"imported lorebook → marinara: {rel}")
        else:
            log(f"marinara lorebook import failed for {rel} ({status}): {result}")
    return imported


def bulk_import_from_sillytavern_tree(state: dict) -> int:
    """Fallback: Marinara ST bulk scan expects data/default-user/ layout under ST root."""
    if not ST_ROOT.is_dir() or not backend_up(MARINARA_PORT):
        return 0
    url = f"http://127.0.0.1:{MARINARA_PORT}/api/import/st-bulk/scan"
    status, scan = http_json("POST", url, {"folderPath": str(ST_ROOT)})
    if status >= 400 or not isinstance(scan, dict) or not scan.get("success"):
        return 0
    chars = scan.get("characters") or []
    if not chars:
        return 0
    new_ids = []
    for item in chars:
        rel = item.get("path", "")
        try:
            p = Path(rel)
            if not p.is_file():
                continue
            key = f"st:{p.name}"
            sig = file_sig(p)
            if state["characters"].get(key) == sig:
                continue
            new_ids.append(item.get("id"))
        except OSError:
            continue
    if not new_ids:
        return 0
    run_url = f"http://127.0.0.1:{MARINARA_PORT}/api/import/st-bulk/run"
    body = {
        "folderPath": str(ST_ROOT),
        "options": {
            "characters": new_ids,
            "chats": False,
            "groupChats": False,
            "presets": False,
            "lorebooks": False,
            "backgrounds": False,
            "personas": False,
        },
    }
    # SSE endpoint — read until done event
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        run_url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        log(f"marinara bulk run failed ({exc.code})")
        return 0
    imported = 0
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        if "imported" in event and isinstance(event["imported"], dict):
            imported = int(event["imported"].get("characters") or 0)
    if imported:
        log(f"marinara bulk imported {imported} character(s) from sillytavern tree")
    return imported


def main() -> int:
    log(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} syncing shared library")
    rsync_shared()
    state = load_state()
    n_chars = import_characters_to_marinara(state)
    n_worlds = import_lorebooks_to_marinara(state)
    if n_chars == 0:
        n_chars = bulk_import_from_sillytavern_tree(state)
    save_state(state)
    if backend_up(LUMIVERSE_PORT):
        log(f"lumiverse staging ready at {STAGING_LUMIVERSE / 'characters'} (import via UI: Characters → Import)")
    log(f"done — marinara: +{n_chars} characters, +{n_worlds} lorebooks")
    return 0


if __name__ == "__main__":
    sys.exit(main())