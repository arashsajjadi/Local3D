#!/usr/bin/env python3
"""Download and verify the model files Local3D needs.

A thin wrapper around the official Hugging Face client (``huggingface_hub``, which ships inside the
ComfyUI portable build): resumable transfers, pinned revisions, size + SHA-256 verification against
``data/models.json``, a disk-space preflight, and atomic placement into ComfyUI's model folders.

Examples (run with the portable build's python, or any python that has huggingface_hub):

    python provision_models.py --models-dir D:\\Local3DModels --check
    python provision_models.py --models-dir D:\\Local3DModels --pack core --pack prompt
    python provision_models.py --models-dir D:\\Local3DModels --json      # JSON lines for the launcher

Exit codes: 0 ok, 1 unexpected error, 2 not enough disk space, 3 network problem, 4 hash mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_DISK, EXIT_NETWORK, EXIT_HASH = 0, 1, 2, 3, 4
DISK_MARGIN = 3 * 2**30  # keep 3 GiB free after the downloads
DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "data" / "models.json"


class Failure(Exception):
    def __init__(self, code: int, message: str, detail: str = ""):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail


class Reporter:
    """Human text by default, JSON lines with --json (consumed by the launcher)."""

    def __init__(self, as_json: bool):
        self.as_json = as_json
        self._last = 0.0

    def event(self, name: str, **kw):
        if self.as_json:
            print(json.dumps({"event": name, **kw}), flush=True)

    def say(self, text: str):
        print(text if not self.as_json else "", end="\n" if not self.as_json else "", flush=True)

    def progress(self, fid: str, done: int, total: int, force: bool = False):
        now = time.monotonic()
        if not force and now - self._last < 0.25:
            return
        self._last = now
        self.event("progress", id=fid, done=done, total=total)


def gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB"


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def select_files(manifest: dict, packs: list[str], only: list[str]) -> list[dict]:
    files = [f for f in manifest["files"] if f["pack"] in packs]
    if only:
        files = [f for f in manifest["files"] if f["id"] in only]
    return files


class VerifyCache:
    """Remember which files were already hashed so launches do not re-hash 15 GB every time."""

    def __init__(self, models_dir: Path):
        self.path = models_dir / ".local3d" / "verified.json"
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def ok(self, f: dict, dest: Path) -> bool:
        try:
            st = dest.stat()
        except OSError:
            return False
        e = self.data.get(f["dest"])
        return bool(e and e["size"] == st.st_size == f["size"] and e["mtime_ns"] == st.st_mtime_ns and e["sha256"] == f["sha256"])

    def remember(self, f: dict, dest: Path):
        st = dest.stat()
        self.data[f["dest"]] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": f["sha256"]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


def sha256_file(path: Path, on_chunk=None) -> str:
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(8 * 2**20):
            h.update(chunk)
            done += len(chunk)
            if on_chunk:
                on_chunk(done)
    return h.hexdigest()


def status_of(f: dict, models_dir: Path, cache: VerifyCache) -> str:
    dest = models_dir / f["dest"]
    if cache.ok(f, dest):
        return "ok"
    if dest.exists() and dest.stat().st_size == f["size"]:
        return "unverified"  # right size, not hashed yet
    return "missing"


def preflight_disk(files: list[dict], models_dir: Path, cache: VerifyCache):
    need = sum(f["size"] for f in files if status_of(f, models_dir, cache) == "missing")
    models_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(models_dir).free
    if need and free < need + DISK_MARGIN:
        raise Failure(
            EXIT_DISK,
            f"Not enough free disk space: {gb(need)} needed, {gb(free)} free in {models_dir.anchor or models_dir}.",
            "Free some space or choose another models folder, then run again. Finished files are kept.",
        )


def make_bar_class(rep: Reporter, fid: str):
    from huggingface_hub.utils import tqdm as hf_tqdm  # official progress-bar class

    class Bar(hf_tqdm):
        def __init__(self, *a, **kw):
            kw["file"] = open(os.devnull, "w")  # keep counting, print nothing
            super().__init__(*a, **kw)

        def update(self, n=1):
            out = super().update(n)
            if self.total:
                rep.progress(fid, int(self.n), int(self.total))
            return out

    return Bar


def download_one(f: dict, models_dir: Path, cache: VerifyCache, rep: Reporter):
    from huggingface_hub import hf_hub_download

    dest = models_dir / f["dest"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    rep.event("file_start", id=f["id"], label=f["label"], size=f["size"])
    rep.say(f"[{f['id']}] {f['label']} ({gb(f['size'])})")

    if status_of(f, models_dir, cache) == "missing":
        staging = models_dir / ".local3d" / "staging" / f["repo"].replace("/", "__")
        try:
            got = Path(
                hf_hub_download(
                    repo_id=f["repo"], filename=f["path"], revision=f["revision"],
                    local_dir=str(staging), tqdm_class=make_bar_class(rep, f["id"]),
                )
            )
        except OSError as e:
            if getattr(e, "errno", None) == 28:
                raise Failure(EXIT_DISK, "The disk is full.", str(e))
            raise Failure(EXIT_NETWORK, "Could not download from huggingface.co. Check your internet connection and run again; the download resumes where it stopped.", f"{type(e).__name__}: {e}")
        except Exception as e:  # network stack exceptions vary by version (httpx, requests, hf errors)
            raise Failure(EXIT_NETWORK, "Could not download from huggingface.co. Check your internet connection and run again; the download resumes where it stopped.", f"{type(e).__name__}: {e}")
        if got.stat().st_size != f["size"]:
            got.unlink(missing_ok=True)
            raise Failure(EXIT_HASH, f"Downloaded file {f['id']} has the wrong size; it was discarded. Run again.", f"expected {f['size']}, got {got.stat().st_size}")
        os.replace(got, dest)

    rep.event("verify", id=f["id"])
    digest = sha256_file(dest, lambda d: rep.progress(f["id"], d, f["size"]))
    if digest != f["sha256"]:
        dest.unlink(missing_ok=True)
        raise Failure(EXIT_HASH, f"Checksum mismatch for {f['id']}; the file was discarded so it cannot be used by mistake. Run again.", f"expected {f['sha256']}, got {digest}")
    cache.remember(f, dest)
    rep.event("file_done", id=f["id"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--models-dir", type=Path, required=True)
    ap.add_argument("--pack", action="append", default=None, help="core (default), prompt")
    ap.add_argument("--only", action="append", default=[], help="download only these file ids (testing)")
    ap.add_argument("--check", action="store_true", help="report what is installed; download nothing")
    ap.add_argument("--json", action="store_true", help="emit JSON lines")
    args = ap.parse_args(argv)
    rep = Reporter(args.json)
    packs = args.pack or ["core"]

    try:
        manifest = load_manifest(args.manifest)
        files = select_files(manifest, packs, args.only)
        models_dir = args.models_dir
        cache = VerifyCache(models_dir)

        if args.check:
            rows = [{"id": f["id"], "pack": f["pack"], "label": f["label"], "size": f["size"], "status": status_of(f, models_dir, cache)} for f in files]
            missing = sum(r["size"] for r in rows if r["status"] != "ok")
            summary = {"files": rows, "missing_bytes": missing, "free_bytes": shutil.disk_usage(models_dir if models_dir.exists() else models_dir.anchor).free}
            print(json.dumps(summary) if args.json else "\n".join(f"{r['status']:10s} {r['id']:22s} {gb(r['size'])}" for r in rows) + f"\nmissing: {gb(missing)}")
            return EXIT_OK

        preflight_disk(files, models_dir, cache)
        for f in files:
            download_one(f, models_dir, cache, rep)
        shutil.rmtree(models_dir / ".local3d" / "staging", ignore_errors=True)
        rep.event("done")
        rep.say("All model files are installed and verified.")
        return EXIT_OK
    except Failure as e:
        rep.event("error", code=e.code, message=e.message, detail=e.detail)
        print(f"ERROR: {e.message}\n{e.detail}", file=sys.stderr, flush=True)
        return e.code
    except Exception as e:
        rep.event("error", code=EXIT_ERROR, message="Unexpected error while preparing model files.", detail=f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
