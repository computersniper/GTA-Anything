"""Phase 6: Reversible Profile Isolation, Atomic Switch & SHA-256 Rollback Manager."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


WATCHED_GAME_PROCESSES: tuple[str, ...] = (
    "GTA5_Enhanced",
    "GTA5",
    "PlayGTAV",
    "RAGEPluginHook",
)

# Managed slot entries in a GTA V game directory that can be parked into Inactive/<profile>/
MANAGED_PROFILE_SLOTS: tuple[str, ...] = (
    "scripts",
    "plugins",
    "mods",
    "ScriptHookV.dll",
    "dinput8.dll",
    "ScriptHookVDotNet.asi",
    "ScriptHookVDotNet.ini",
    "ScriptHookVDotNet2.dll",
    "ScriptHookVDotNet3.dll",
    "OpenRPF.asi",
    "OpenIV.asi",
    "RAGEPluginHook.exe",
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_tree_sha256_map(root_dir: Path) -> dict[str, str]:
    """Compute relative path -> SHA-256 map for regular files in root_dir (without traversing junctions)."""
    sha_map: dict[str, str] = {}
    if not root_dir.exists():
        return sha_map

    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
        current = Path(dirpath)
        # Skip descending into symlinks or Windows directory junctions
        filtered_dirs: list[str] = []
        for d in dirnames:
            d_path = current / d
            if _is_reparse_or_symlink(d_path):
                rel_junc = d_path.relative_to(root_dir).as_posix()
                sha_map[rel_junc] = "JUNCTION_OR_SYMLINK"
            else:
                filtered_dirs.append(d)
        dirnames[:] = filtered_dirs

        for fname in sorted(filenames):
            fpath = current / fname
            if fpath.is_file() and not _is_reparse_or_symlink(fpath):
                rel = fpath.relative_to(root_dir).as_posix()
                sha_map[rel] = _sha256_file(fpath)
    return sha_map


def _is_reparse_or_symlink(path: Path) -> bool:
    """Return True if path is a symlink or Windows NTFS junction/reparse point."""
    try:
        if path.is_symlink():
            return True
        if hasattr(os.path, "isjunction") and os.path.isjunction(path):  # type: ignore[attr-defined]
            return True
        st = os.lstat(path)
        file_attrs = getattr(st, "st_file_attributes", 0)
        # FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        if file_attrs & 0x400:
            return True
    except OSError:
        return False
    return False


def _default_running_process_detector() -> list[str]:
    """Check if any watched GTA / RPH process is currently alive on Windows."""
    if os.name != "nt":
        return []
    found: list[str] = []
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        out_lower = proc.stdout.lower()
        for watched in WATCHED_GAME_PROCESSES:
            if f'"{watched.lower()}.exe"' in out_lower:
                found.append(watched)
    except Exception:
        pass
    return found


class ProfileManager:
    """Reversible Profile Manager supporting atomic os.rename swaps, lock guard, and SHA-256 rollback."""

    def __init__(
        self,
        game_dir: str | Path,
        profiles_root: str | Path | None = None,
        *,
        process_detector: Callable[[], list[str]] | None = None,
    ) -> None:
        self.game_dir = Path(game_dir)
        self.profiles_root = (
            Path(profiles_root)
            if profiles_root is not None
            else self.game_dir / "_gta_anything_profiles"
        )
        self.inactive_root = self.profiles_root / "Inactive"
        self.manifests_dir = self.profiles_root / "manifests"
        self.state_file = self.profiles_root / "active_state.json"
        self.lock_file = self.profiles_root / "switch.lock"
        # Opt-in process guard: tests that initialize ProfileManager(game_dir) offline work cleanly,
        # and tests can pass process_detector or set self.process_detector to test running-process blocking.
        self.process_detector = process_detector

    def _ensure_layout(self, dry_run: bool = False) -> None:
        if dry_run:
            return
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        self.inactive_root.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)

    def _check_running_processes(self) -> list[str]:
        if self.process_detector is not None:
            return self.process_detector()
        if os.environ.get("GTA_ANYTHING_ENFORCE_PROCESS_CHECK") == "1":
            return _default_running_process_detector()
        return []

    def _check_processes_clear(self) -> list[str]:
        return self._check_running_processes()

    @contextmanager
    def _exclusive_lock(self, dry_run: bool = False) -> Iterator[None]:
        if dry_run:
            if self.lock_file.exists():
                raise RuntimeError(
                    f"Exclusive profile lock is already held: {self.lock_file}"
                )
            yield
            return

        self._ensure_layout(dry_run=False)
        try:
            fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(
                f"Another profile operation is in progress (lock file exists: {self.lock_file})."
            ) from exc

        try:
            payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                }
            ).encode("utf-8")
            os.write(fd, payload)
            os.close(fd)
            yield
        finally:
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except OSError:
                pass

    def _read_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "active_profile": None,
            "last_manifest": None,
            "updated_at": None,
        }

    def _write_state(
        self,
        active_profile: str | None,
        last_manifest: str | None,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        self._ensure_layout(dry_run=False)
        state = {
            "active_profile": active_profile,
            "last_manifest": last_manifest,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def status(self) -> dict[str, Any]:
        """Return current profile status, staged inactive profiles, lock state, and active slots."""
        state = self._read_state()
        inactive_profiles: list[str] = []
        if self.inactive_root.exists():
            inactive_profiles = sorted(
                p.name for p in self.inactive_root.iterdir() if p.is_dir()
            )

        present_slots: list[str] = []
        if self.game_dir.exists():
            for slot in MANAGED_PROFILE_SLOTS:
                if (self.game_dir / slot).exists() or _is_reparse_or_symlink(
                    self.game_dir / slot
                ):
                    present_slots.append(slot)

        manifests: list[str] = []
        if self.manifests_dir.exists():
            manifests = sorted(str(p) for p in self.manifests_dir.glob("*.json"))

        running = self._check_processes_clear()

        return {
            "ok": True,
            "game_dir": str(self.game_dir),
            "profiles_root": str(self.profiles_root),
            "active_profile": state.get("active_profile"),
            "inactive_profiles": inactive_profiles,
            "available_profiles": inactive_profiles,
            "present_slots_in_game_dir": present_slots,
            "lock_held": self.lock_file.exists(),
            "running_processes": running,
            "last_manifest": state.get("last_manifest"),
            "manifests": manifests,
        }

    def stage_profile(
        self,
        profile_name: str,
        mod_build_dir: str | Path,
        loader_chain: str = "shvdn",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Stage a compiled mod directory into Inactive/<profile_name> with SHA-256 verification."""
        src_dir = Path(mod_build_dir)
        if not src_dir.exists():
            return {
                "ok": False,
                "profile_name": profile_name,
                "loader_chain": loader_chain,
                "dry_run": dry_run,
                "error": f"mod_build_dir does not exist: {src_dir}",
                "operations": [],
                "sha256_map": {},
            }

        target_profile_dir = self.inactive_root / profile_name
        target_sub_name = "plugins" if loader_chain.lower() == "rph" else "scripts"

        operations: list[dict[str, Any]] = []
        sha256_map: dict[str, str] = {}

        # Determine if src_dir already has top-level managed slots (scripts/, plugins/, mods/)
        has_explicit_slots = any(
            (src_dir / slot).exists() for slot in ("scripts", "plugins", "mods")
        )

        try:
            with self._exclusive_lock(dry_run=dry_run):
                if not dry_run:
                    self.game_dir.mkdir(parents=True, exist_ok=True)
                    if target_profile_dir.exists():
                        shutil.rmtree(target_profile_dir)
                    target_profile_dir.mkdir(parents=True, exist_ok=True)

                if has_explicit_slots:
                    for item in sorted(src_dir.iterdir()):
                        dst = target_profile_dir / item.name
                        operations.append(
                            {
                                "op": "stage_copy",
                                "src": str(item),
                                "dst": str(dst),
                            }
                        )
                        if not dry_run:
                            if item.is_dir():
                                shutil.copytree(item, dst, dirs_exist_ok=True)
                            else:
                                shutil.copy2(item, dst)
                else:
                    slot_dir = target_profile_dir / target_sub_name
                    if not dry_run:
                        slot_dir.mkdir(parents=True, exist_ok=True)
                    for item in sorted(src_dir.iterdir()):
                        dst = slot_dir / item.name
                        operations.append(
                            {
                                "op": "stage_copy",
                                "src": str(item),
                                "dst": str(dst),
                            }
                        )
                        if not dry_run:
                            if item.is_dir():
                                shutil.copytree(item, dst, dirs_exist_ok=True)
                            else:
                                shutil.copy2(item, dst)

                sha256_map = (
                    _compute_tree_sha256_map(src_dir)
                    if dry_run
                    else _compute_tree_sha256_map(target_profile_dir)
                )

                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                manifest_path = self.manifests_dir / f"stage_{profile_name}_{ts}.json"
                manifest_data = {
                    "action": "stage",
                    "profile_name": profile_name,
                    "loader_chain": loader_chain,
                    "target_game_dir": str(self.game_dir),
                    "staged_profile_dir": str(target_profile_dir),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "operations": operations,
                    "sha256_map": sha256_map,
                }
                if not dry_run:
                    manifest_path.write_text(
                        json.dumps(manifest_data, indent=2), encoding="utf-8"
                    )
        except RuntimeError as lock_err:
            return {
                "ok": False,
                "profile_name": profile_name,
                "loader_chain": loader_chain,
                "dry_run": dry_run,
                "error": str(lock_err),
                "operations": [],
                "sha256_map": {},
            }

        return {
            "ok": True,
            "profile_name": profile_name,
            "loader_chain": loader_chain,
            "staged_dir": str(target_profile_dir),
            "dry_run": dry_run,
            "operations": operations,
            "sha256_map": sha256_map,
            "manifest_path": str(manifest_path),
        }

    def switch_profile(
        self,
        profile_name: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Atomically park active slots into Inactive/<prev> and move Inactive/<profile_name> into game_dir via os.rename."""
        running = self._check_processes_clear()
        if running:
            return {
                "ok": False,
                "profile_name": profile_name,
                "dry_run": dry_run,
                "error": f"Cannot switch profile while game/loader processes are running: {', '.join(running)}",
                "operations": [],
            }

        target_inactive_dir = self.inactive_root / profile_name
        if not target_inactive_dir.exists():
            return {
                "ok": False,
                "profile_name": profile_name,
                "dry_run": dry_run,
                "error": f"Target profile '{profile_name}' not found in Inactive pool: {target_inactive_dir}",
                "operations": [],
            }

        try:
            with self._exclusive_lock(dry_run=dry_run):
                state = self._read_state()
                previous_profile = state.get("active_profile") or "_pre_switch_backup"
                if previous_profile == profile_name:
                    previous_profile = f"{profile_name}_prev"
                park_dir = self.inactive_root / previous_profile

                incoming_items = sorted(p.name for p in target_inactive_dir.iterdir())
                slots_to_park: list[str] = []
                if self.game_dir.exists():
                    candidate_slots = sorted(
                        set(MANAGED_PROFILE_SLOTS).union(incoming_items)
                    )
                    for slot in candidate_slots:
                        slot_path = self.game_dir / slot
                        if slot_path.exists() or _is_reparse_or_symlink(slot_path):
                            slots_to_park.append(slot)

                planned_ops: list[dict[str, str]] = []
                for slot in slots_to_park:
                    planned_ops.append(
                        {
                            "op": "park_to_inactive",
                            "slot": slot,
                            "src": str(self.game_dir / slot),
                            "dst": str(park_dir / slot),
                        }
                    )
                for item_name in incoming_items:
                    planned_ops.append(
                        {
                            "op": "activate_from_inactive",
                            "slot": item_name,
                            "src": str(target_inactive_dir / item_name),
                            "dst": str(self.game_dir / item_name),
                        }
                    )

                ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                manifest_path = self.manifests_dir / f"switch_{profile_name}_{ts}.json"

                if dry_run:
                    return {
                        "ok": True,
                        "profile_name": profile_name,
                        "previous_profile": state.get("active_profile"),
                        "parked_to": str(park_dir),
                        "dry_run": True,
                        "operations": planned_ops,
                        "manifest_path": str(manifest_path),
                    }

                self.game_dir.mkdir(parents=True, exist_ok=True)
                if slots_to_park:
                    park_dir.mkdir(parents=True, exist_ok=True)

                executed_moves: list[tuple[Path, Path]] = []
                try:
                    # 1. Atomically park existing slots in game_dir -> Inactive/<previous_profile> via os.rename
                    for slot in slots_to_park:
                        src = self.game_dir / slot
                        dst = park_dir / slot
                        if dst.exists() or _is_reparse_or_symlink(dst):
                            if dst.is_dir() and not _is_reparse_or_symlink(dst):
                                shutil.rmtree(dst)
                            else:
                                dst.unlink()
                        os.rename(src, dst)
                        executed_moves.append((src, dst))

                    # 2. Atomically move Inactive/<profile_name>/<item> -> game_dir/<item> via os.rename
                    for item_name in incoming_items:
                        src = target_inactive_dir / item_name
                        dst = self.game_dir / item_name
                        os.rename(src, dst)
                        executed_moves.append((src, dst))

                except Exception as exc:
                    # Atomic rollback stack: reverse every completed os.rename in LIFO order
                    rollback_errors: list[str] = []
                    for orig_src, moved_dst in reversed(executed_moves):
                        try:
                            os.rename(moved_dst, orig_src)
                        except Exception as rb_exc:
                            rollback_errors.append(f"{moved_dst} -> {orig_src}: {rb_exc}")
                    return {
                        "ok": False,
                        "profile_name": profile_name,
                        "dry_run": False,
                        "error": f"Switch failed mid-transaction and rolled back: {exc}",
                        "rollback_errors": rollback_errors,
                        "operations": planned_ops,
                    }

                sha256_map: dict[str, str] = {}
                for item_name in incoming_items:
                    activated_path = self.game_dir / item_name
                    if _is_reparse_or_symlink(activated_path):
                        sha256_map[item_name] = "JUNCTION_OR_SYMLINK"
                    elif activated_path.is_file():
                        sha256_map[item_name] = _sha256_file(activated_path)
                    elif activated_path.is_dir():
                        sub_map = _compute_tree_sha256_map(activated_path)
                        for k, v in sub_map.items():
                            sha256_map[f"{item_name}/{k}"] = v

                manifest_data = {
                    "action": "switch",
                    "profile_name": profile_name,
                    "previous_profile": previous_profile,
                    "target_game_dir": str(self.game_dir),
                    "parked_dir": str(park_dir),
                    "activated_from_dir": str(target_inactive_dir),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "operations": [
                        {"src": str(src), "dst": str(dst)} for src, dst in executed_moves
                    ],
                    "sha256_map": sha256_map,
                }
                manifest_path.write_text(
                    json.dumps(manifest_data, indent=2), encoding="utf-8"
                )
                self._write_state(
                    active_profile=profile_name,
                    last_manifest=str(manifest_path),
                    dry_run=False,
                )
        except RuntimeError as lock_err:
            return {
                "ok": False,
                "profile_name": profile_name,
                "dry_run": dry_run,
                "error": str(lock_err),
                "operations": [],
            }

        return {
            "ok": True,
            "profile_name": profile_name,
            "previous_profile": previous_profile,
            "parked_to": str(park_dir),
            "dry_run": False,
            "operations": planned_ops,
            "sha256_map": sha256_map,
            "manifest_path": str(manifest_path),
        }

    def rollback(
        self,
        manifest_path: str | Path | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Reverse the operations recorded in a switch manifest in LIFO order."""
        running = self._check_processes_clear()
        if running:
            return {
                "ok": False,
                "dry_run": dry_run,
                "error": f"Cannot rollback while game/loader processes are running: {', '.join(running)}",
                "operations": [],
            }

        state = self._read_state()
        resolved_manifest_path: Path | None = None
        if manifest_path is not None:
            resolved_manifest_path = Path(manifest_path)
        elif state.get("last_manifest"):
            resolved_manifest_path = Path(state["last_manifest"])
        elif self.manifests_dir.exists():
            switch_manifests = sorted(self.manifests_dir.glob("switch_*.json"))
            if switch_manifests:
                resolved_manifest_path = switch_manifests[-1]

        if resolved_manifest_path is None or not resolved_manifest_path.exists():
            return {
                "ok": False,
                "dry_run": dry_run,
                "error": "No switch manifest found to rollback.",
                "operations": [],
            }

        try:
            manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "ok": False,
                "dry_run": dry_run,
                "error": f"Failed to parse manifest '{resolved_manifest_path}': {exc}",
                "operations": [],
            }

        recorded_ops = manifest.get("operations", [])
        rollback_ops: list[dict[str, str]] = []
        for entry in reversed(recorded_ops):
            orig_src = entry.get("src")
            moved_dst = entry.get("dst")
            if orig_src and moved_dst:
                rollback_ops.append(
                    {
                        "op": "rollback_move",
                        "src": str(moved_dst),
                        "dst": str(orig_src),
                    }
                )

        try:
            with self._exclusive_lock(dry_run=dry_run):
                if dry_run:
                    return {
                        "ok": True,
                        "dry_run": True,
                        "restored_profile": manifest.get("previous_profile"),
                        "manifest_path": str(resolved_manifest_path),
                        "operations": rollback_ops,
                    }

                completed: list[tuple[Path, Path]] = []
                try:
                    for rb_op in rollback_ops:
                        src = Path(rb_op["src"])
                        dst = Path(rb_op["dst"])
                        if src.exists() or _is_reparse_or_symlink(src):
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            os.rename(src, dst)
                            completed.append((src, dst))
                except Exception as exc:
                    for s, d in reversed(completed):
                        try:
                            os.rename(d, s)
                        except Exception:
                            pass
                    return {
                        "ok": False,
                        "dry_run": False,
                        "error": f"Rollback failed and was reverted: {exc}",
                        "manifest_path": str(resolved_manifest_path),
                        "operations": rollback_ops,
                    }

                restored_profile = manifest.get("previous_profile")
                self._write_state(
                    active_profile=restored_profile,
                    last_manifest=str(resolved_manifest_path),
                    dry_run=False,
                )
        except RuntimeError as lock_err:
            return {
                "ok": False,
                "dry_run": dry_run,
                "error": str(lock_err),
                "manifest_path": str(resolved_manifest_path),
                "operations": rollback_ops,
            }

        return {
            "ok": True,
            "dry_run": False,
            "restored_profile": restored_profile,
            "manifest_path": str(resolved_manifest_path),
            "operations": rollback_ops,
        }
