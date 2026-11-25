"""Build identity, loader chain specifications, reversible deployment manifests,
and the 7-Layer Acceptance Evidence Ladder (L1-L7).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


ACCEPTANCE_LAYERS: list[dict[str, Any]] = [
    {
        "layer": 1,
        "id": "L1",
        "name": "Static Config & Asset Integrity",
        "phase": "static_verification",
        "description": "Configuration files, Gameplay IR, dlclist.xml, and .yft/.ytd RSC headers are readable and pass static edition gates.",
        "evidence_required": "validate-ir & asset-check JSON reports with zero blocking errors",
    },
    {
        "layer": 2,
        "id": "L2",
        "name": "Loader Chain Recognition",
        "phase": "loader_boot",
        "description": "ScriptHookV / ASI Loader / ScriptHookVDotNet or RAGEPluginHook recognizes the game build and mounts the assembly.",
        "evidence_required": "ScriptHookV.log build alias match + SHVDN/RPH assembly load event",
    },
    {
        "layer": 3,
        "id": "L3",
        "name": "Script Initialization & Session Ready",
        "phase": "script_init",
        "description": "Mod entrypoint initializes cleanly, loads JSON configuration, and creates an empty WorldSession lease table.",
        "evidence_required": "PhasedJsonLogger L3 event (`ConfigLoaded` / `SessionInitialized`)",
    },
    {
        "layer": 4,
        "id": "L4",
        "name": "Decoupled Menu Invocation & Hotkey Safety",
        "phase": "ui_interaction",
        "description": "Activation hotkey opens menu without conflict; scrolling items updates static cards/2D sprites without live 3D vehicle spawning.",
        "evidence_required": "PhasedJsonLogger L4 event (`MenuOpened` / `StaticPreviewUpdated`) with zero NullReferenceException",
    },
    {
        "layer": 5,
        "id": "L5",
        "name": "Safe Model Streaming & Shift Start",
        "phase": "resource_streaming_and_spawn",
        "description": "Preferred or vanilla fallback models stream within timeout (releasing timed-out handles) and spawn verified non-null world entities.",
        "evidence_required": "PhasedJsonLogger L5 event (`ModelStreamResolved` + `ServiceVehicleSpawned`)",
    },
    {
        "layer": 6,
        "id": "L6",
        "name": "Core Operational Loop Completion",
        "phase": "active_operation",
        "description": "Full operational cycle completes (ordered stop dwell, door/passenger boarding or dispatch zone resolution, fare/reward settlement).",
        "evidence_required": "PhasedJsonLogger L6 events (`StopCompleted` / `CalloutResolved` / `ShiftSummaryRecorded`)",
    },
    {
        "layer": 7,
        "id": "L7",
        "name": "Deterministic WorldSession Teardown",
        "phase": "cleanup",
        "description": "Normal completion or abort deterministically releases all leased vehicles, peds, blips, cameras, and model handles.",
        "evidence_required": "PhasedJsonLogger L7 event (`TeardownCompleted`, `leasedEntitiesRemaining: 0`)",
    },
]


@dataclass
class GameBuildIdentity:
    """Explicit dual-build representation distinguishing disk PE version from ScriptHookV enum alias."""

    edition: str
    exe_version: str
    shv_build_alias: str | None = None
    exe_name: str = "GTA5_Enhanced.exe"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameBuildIdentity:
        edition = str(data.get("edition", "enhanced_gen9"))
        default_exe = (
            "GTA5_Enhanced.exe" if edition == "enhanced_gen9" else "GTA5.exe"
        )
        raw_alias = data.get("shv_build_alias")
        return cls(
            edition=edition,
            exe_version=str(data.get("exe_version", "unknown")),
            shv_build_alias=str(raw_alias) if raw_alias else None,
            exe_name=str(data.get("exe_name", default_exe)),
        )


@dataclass
class LoaderChainSpec:
    """Specification of one of the two distinct GTA V mod loading chains (`shvdn` vs `rph`)."""

    chain_id: str
    required_files: list[str] = field(default_factory=list)
    log_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoaderChainSpec:
        return cls(
            chain_id=str(data.get("chain_id", "shvdn")),
            required_files=list(data.get("required_files", [])),
            log_files=list(data.get("log_files", [])),
        )


DEFAULT_LOADER_CHAINS: dict[str, LoaderChainSpec] = {
    "shvdn": LoaderChainSpec(
        chain_id="shvdn",
        required_files=[
            "dinput8.dll",
            "ScriptHookV.dll",
            "ScriptHookVDotNet.asi",
        ],
        log_files=[
            "ScriptHookV.log",
            "ScriptHookVDotNet.log",
        ],
    ),
    "rph": LoaderChainSpec(
        chain_id="rph",
        required_files=[
            "RAGEPluginHook.exe",
        ],
        log_files=[
            "RagePluginHook.log",
        ],
    ),
}


@dataclass
class DeploymentManifest:
    """Reversible deployment manifest recording operations and SHA-256 checksums for rollback."""

    profile_name: str
    mod_id: str
    target_game_dir: str
    edition: str
    created_at: str
    operations: list[dict[str, Any]] = field(default_factory=list)
    sha256_map: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeploymentManifest:
        return cls(
            profile_name=str(data.get("profile_name", "default")),
            mod_id=str(data.get("mod_id", "unknown_mod")),
            target_game_dir=str(data.get("target_game_dir", "")),
            edition=str(data.get("edition", "enhanced_gen9")),
            created_at=str(data.get("created_at", "")),
            operations=list(data.get("operations", [])),
            sha256_map=dict(data.get("sha256_map", {})),
        )

    @classmethod
    def from_json(cls, raw_json: str) -> DeploymentManifest:
        return cls.from_dict(json.loads(raw_json))
