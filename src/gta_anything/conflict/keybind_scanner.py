"""Multi-Format GTA V Keybind Scanner, Chord Normalizer, Conflict Evaluator & Safe Rebind Recommender."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

MAX_CONFIG_FILE_BYTES = 2 * 1024 * 1024  # 2 MB cap to avoid scanning large binaries/logs

BINARY_OR_IGNORED_EXTENSIONS = {
    ".rpf",
    ".exe",
    ".dll",
    ".asi",
    ".yft",
    ".ytd",
    ".ydr",
    ".ydd",
    ".ybn",
    ".ymap",
    ".ytyp",
    ".awc",
    ".dds",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".log",
    ".pdb",
    ".zip",
    ".7z",
    ".rar",
    ".bak",
}

# Virtual-Key (Win32 VK_*) code table -> canonical key name
VK_CODE_MAP: dict[int, str] = {
    0x08: "Back",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x13: "Pause",
    0x14: "CapsLock",
    0x1B: "Escape",
    0x20: "Space",
    0x21: "PageUp",
    0x22: "PageDown",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2C: "PrintScreen",
    0x2D: "Insert",
    0x2E: "Delete",
    **{0x30 + i: str(i) for i in range(10)},
    **{0x41 + i: chr(ord("A") + i) for i in range(26)},
    **{0x60 + i: f"NumPad{i}" for i in range(10)},
    0x6A: "Multiply",
    0x6B: "Add",
    0x6C: "Separator",
    0x6D: "Subtract",
    0x6E: "Decimal",
    0x6F: "Divide",
    **{0x70 + i: f"F{i + 1}" for i in range(24)},  # 0x70..0x87 -> F1..F24
    0x90: "NumLock",
    0x91: "Scroll",
    0xA0: "Shift",  # VK_LSHIFT
    0xA1: "Shift",  # VK_RSHIFT
    0xA2: "Ctrl",   # VK_LCONTROL
    0xA3: "Ctrl",   # VK_RCONTROL
    0xA4: "Alt",    # VK_LMENU
    0xA5: "Alt",    # VK_RMENU
    0xBA: "OemSemicolon",
    0xBB: "Oemplus",
    0xBC: "Oemcomma",
    0xBD: "OemMinus",
    0xBE: "OemPeriod",
    0xBF: "OemQuestion",
    0xC0: "Oemtilde",
    0xDB: "OemOpenBrackets",
    0xDC: "OemPipe",
    0xDD: "OemCloseBrackets",
    0xDE: "OemQuotes",
}

# WinForms System.Windows.Forms.Keys / RPH / SHVDN alias table (lowercased -> canonical)
KEY_ALIAS_MAP: dict[str, str] = {
    # Modifiers
    "shift": "Shift",
    "shiftkey": "Shift",
    "lshift": "Shift",
    "lshiftkey": "Shift",
    "leftshift": "Shift",
    "leftshiftkey": "Shift",
    "rshift": "Shift",
    "rshiftkey": "Shift",
    "rightshift": "Shift",
    "rightshiftkey": "Shift",
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "controlkey": "Ctrl",
    "lctrl": "Ctrl",
    "lcontrol": "Ctrl",
    "lcontrolkey": "Ctrl",
    "leftctrl": "Ctrl",
    "leftcontrol": "Ctrl",
    "leftcontrolkey": "Ctrl",
    "rctrl": "Ctrl",
    "rcontrol": "Ctrl",
    "rcontrolkey": "Ctrl",
    "rightctrl": "Ctrl",
    "rightcontrol": "Ctrl",
    "rightcontrolkey": "Ctrl",
    "alt": "Alt",
    "menu": "Alt",
    "lalt": "Alt",
    "lmenu": "Alt",
    "leftalt": "Alt",
    "leftmenu": "Alt",
    "ralt": "Alt",
    "rmenu": "Alt",
    "rightalt": "Alt",
    "rightmenu": "Alt",
    # Special / Navigation keys
    "ins": "Insert",
    "insert": "Insert",
    "del": "Delete",
    "delete": "Delete",
    "ret": "Enter",
    "return": "Enter",
    "enter": "Enter",
    "esc": "Escape",
    "escape": "Escape",
    "space": "Space",
    "spacebar": "Space",
    "tab": "Tab",
    "back": "Back",
    "backspace": "Back",
    "home": "Home",
    "end": "End",
    "pgup": "PageUp",
    "pageup": "PageUp",
    "prior": "PageUp",
    "pgdn": "PageDown",
    "pagedown": "PageDown",
    "next": "PageDown",
    "up": "Up",
    "uparrow": "Up",
    "down": "Down",
    "downarrow": "Down",
    "left": "Left",
    "leftarrow": "Left",
    "right": "Right",
    "rightarrow": "Right",
    "capslock": "CapsLock",
    "capital": "CapsLock",
    "numlock": "NumLock",
    "scroll": "Scroll",
    "scrolllock": "Scroll",
    "pause": "Pause",
    "printscreen": "PrintScreen",
    "snapshot": "PrintScreen",
    # Numpad & arithmetic
    **{f"numpad{i}": f"NumPad{i}" for i in range(10)},
    **{f"num{i}": f"NumPad{i}" for i in range(10)},
    "multiply": "Multiply",
    "add": "Add",
    "subtract": "Subtract",
    "decimal": "Decimal",
    "divide": "Divide",
    # Top-row digits (WinForms D0..D9)
    **{f"d{i}": str(i) for i in range(10)},
    **{str(i): str(i) for i in range(10)},
    # Function keys F1..F24
    **{f"f{i}": f"F{i}" for i in range(1, 25)},
    # Letters A..Z
    **{chr(ord("a") + i): chr(ord("A") + i) for i in range(26)},
    # OEM punctuation
    "oemtilde": "Oemtilde",
    "tilde": "Oemtilde",
    "backquote": "Oemtilde",
    "grave": "Oemtilde",
    "oemminus": "OemMinus",
    "oemplus": "Oemplus",
    "oemopenbrackets": "OemOpenBrackets",
    "oemclosebrackets": "OemCloseBrackets",
    "oempipe": "OemPipe",
    "oembackslash": "OemPipe",
    "oemsemicolon": "OemSemicolon",
    "oemquotes": "OemQuotes",
    "oemcomma": "Oemcomma",
    "oemperiod": "OemPeriod",
    "oemquestion": "OemQuestion",
    # Controller buttons
    "dpadup": "DPadUp",
    "dpaddown": "DPadDown",
    "dpadleft": "DPadLeft",
    "dpadright": "DPadRight",
    "leftshoulder": "LeftShoulder",
    "rightshoulder": "RightShoulder",
    "leftthumb": "LeftThumb",
    "rightthumb": "RightThumb",
    "lefttrigger": "LeftTrigger",
    "righttrigger": "RightTrigger",
    "lshoulder": "LeftShoulder",
    "rshoulder": "RightShoulder",
    "lthumb": "LeftThumb",
    "rthumb": "RightThumb",
}

NULL_KEY_TOKENS = {
    "",
    "none",
    "null",
    "nil",
    "false",
    "disabled",
    "disable",
    "off",
    "no",
    "nokey",
    "unbound",
    "unassigned",
    "0",
    "0x0",
    "0x00",
    "-1",
}

CANONICAL_MODIFIERS = ("Ctrl", "Alt", "Shift")

CONTROLLER_BUTTON_KEYS = {
    "DPadUp",
    "DPadDown",
    "DPadLeft",
    "DPadRight",
    "LeftShoulder",
    "RightShoulder",
    "LeftThumb",
    "RightThumb",
    "LeftTrigger",
    "RightTrigger",
}

VALID_CANONICAL_KEYS: set[str] = set(VK_CODE_MAP.values()) | set(KEY_ALIAS_MAP.values())

# Built-in baseline conflict knowledge base across RPH, SHVDN, Trainers, Vanilla & LSPDFR
BASELINE_KEYBIND_KNOWLEDGE_BASE: tuple[dict[str, Any], ...] = (
    {
        "canonical_chord": "F4",
        "canonical_key": "F4",
        "canonical_modifier": None,
        "owner_mod": "RAGEPluginHook",
        "setting_name": "ConsoleKey",
        "context_scope": "global_loader",
        "reason": "F4 is the default RAGEPluginHook console toggle and ScriptHookV NativeTrainer hotkey.",
        "suggestion": "Use a modified chord like LeftShift+F9, LeftShift+F10, or LeftControl+F9.",
    },
    {
        "canonical_chord": "Insert",
        "canonical_key": "Insert",
        "canonical_modifier": None,
        "owner_mod": "ScriptHookVDotNet",
        "setting_name": "ReloadKey",
        "context_scope": "global_loader",
        "reason": "Insert is the default ScriptHookVDotNet script reload hotkey.",
        "suggestion": "Never bind mod menus to Insert; use LeftShift+F9 or LeftShift+F10.",
    },
    {
        "canonical_chord": "F3",
        "canonical_key": "F3",
        "canonical_modifier": None,
        "owner_mod": "SimpleTrainer",
        "setting_name": "MenuKey",
        "context_scope": "mod_menu",
        "reason": "F3 is the default activation hotkey for Simple Trainer (TrainerV).",
        "suggestion": "Avoid unmodified F3; use F7/F10 or a Shift/Ctrl modifier chord.",
    },
    {
        "canonical_chord": "F8",
        "canonical_key": "F8",
        "canonical_modifier": None,
        "owner_mod": "Menyoo",
        "setting_name": "MenuKey",
        "context_scope": "mod_menu",
        "reason": "F8 is the default activation key for Menyoo PC trainer.",
        "suggestion": "Avoid unmodified F8; use F7/F10 or a Shift/Ctrl modifier chord.",
    },
    {
        "canonical_chord": "E",
        "canonical_key": "E",
        "canonical_modifier": None,
        "owner_mod": "GTAV_Vanilla",
        "setting_name": "INPUT_CONTEXT_HORN",
        "context_scope": "in_vehicle",
        "reason": "E (INPUT_CONTEXT / INPUT_VEH_HORN) controls vehicle horn, emergency sirens, and vanilla context interactions.",
        "suggestion": "Avoid E for menu activation; even Shift+E can sound the vehicle horn unless INPUT_VEH_HORN is suppressed each tick.",
    },
    {
        "canonical_chord": "B",
        "canonical_key": "B",
        "canonical_modifier": None,
        "owner_mod": "LSPDFR",
        "setting_name": "BackupMenuKey",
        "context_scope": "on_duty_police",
        "reason": "Unmodified B opens the LSPDFR Backup Menu when on duty.",
        "suggestion": "Use a function key chord (e.g. LeftShift+F9, LeftShift+F10) or isolate SHVDN and RPH profiles.",
    },
    {
        "canonical_chord": "N",
        "canonical_key": "N",
        "canonical_modifier": None,
        "owner_mod": "LSPDFR",
        "setting_name": "InteractionMenuKey",
        "context_scope": "on_duty_police",
        "reason": "Unmodified N opens the LSPDFR Interaction Menu / Police Radio.",
        "suggestion": "Use a function key chord (e.g. LeftShift+F9, LeftShift+F10) or isolate SHVDN and RPH profiles.",
    },
    {
        "canonical_chord": "Y",
        "canonical_key": "Y",
        "canonical_modifier": None,
        "owner_mod": "LSPDFR",
        "setting_name": "AcceptCalloutKey",
        "context_scope": "on_duty_police",
        "reason": "Unmodified Y accepts incoming LSPDFR dispatch callouts.",
        "suggestion": "Use a function key chord (e.g. LeftShift+F9, LeftShift+F10) or isolate SHVDN and RPH profiles.",
    },
)

CANDIDATE_SAFE_CHORDS: tuple[tuple[str, str | None, str], ...] = (
    ("F9", "LeftShift", "Ergonomic Shift+F9 function chord clear of RPH F4, SHVDN Insert, Trainers F3/F8, and active mod bindings."),
    ("F10", "LeftShift", "Ergonomic Shift+F10 function chord clear of RPH, SHVDN, Trainers, and active mod bindings."),
    ("F9", "LeftControl", "Clean Ctrl+F9 function chord with zero loader or active mod collision."),
    ("F10", "LeftControl", "Clean Ctrl+F10 function chord with zero loader or active mod collision."),
    ("F7", "LeftAlt", "Clean Alt+F7 function chord isolated from vanilla gameplay and trainer hotkeys."),
    ("F7", "LeftShift", "Clean Shift+F7 function chord isolated from vanilla gameplay and trainer hotkeys."),
    ("F7", "LeftControl", "Clean Ctrl+F7 function chord isolated from vanilla gameplay and trainer hotkeys."),
    ("F11", "LeftShift", "Clean Shift+F11 function chord free of active profile bindings."),
    ("F11", "LeftControl", "Clean Ctrl+F11 function chord free of active profile bindings."),
    ("F10", "LeftAlt", "Clean Alt+F10 function chord free of active profile bindings."),
    ("F9", "LeftAlt", "Clean Alt+F9 function chord free of active profile bindings."),
    ("F6", "LeftShift", "Clean Shift+F6 function chord free of active profile bindings."),
    ("F6", "LeftControl", "Clean Ctrl+F6 function chord free of active profile bindings."),
    ("F10", None, "Unmodified F10 function key clear of default RPH/SHVDN/Trainer hotkeys."),
    ("F7", None, "Unmodified F7 function key clear of default RPH/SHVDN/Trainer hotkeys."),
)


def _strip_inline_comment(raw: str) -> str:
    """Strip inline .ini/.cfg comments (;, //, #) and surrounding quotes."""
    val = raw.strip()
    for marker in ("//", ";", " #", "\t#"):
        idx = val.find(marker)
        if idx != -1:
            val = val[:idx].strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
        val = val[1:-1].strip()
    return val


def normalize_key_name(key: str | None) -> str | None:
    """Normalize WinForms Keys, RPH/SHVDN key aliases, and Virtual-Key hex codes to canonical key names."""
    if key is None:
        return None

    cleaned = _strip_inline_comment(str(key))
    if not cleaned:
        return None

    low = cleaned.lower()
    if low in NULL_KEY_TOKENS:
        return None

    # Strip namespace/enum prefix like System.Windows.Forms.Keys.LShiftKey or Keys.F9
    if "." in cleaned and not re.match(r"^\d+\.\d+$", cleaned):
        cleaned = cleaned.split(".")[-1].strip()
        low = cleaned.lower()
        if low in NULL_KEY_TOKENS:
            return None

    # Virtual-Key hex code (e.g. 0x70..0x87 -> F1..F24, 0x2D -> Insert, 0x0D -> Enter)
    if low.startswith("0x"):
        try:
            vk_int = int(low, 16)
            if vk_int == 0:
                return None
            if vk_int in VK_CODE_MAP:
                return VK_CODE_MAP[vk_int]
        except ValueError:
            return None

    # Direct lookup in alias map
    if low in KEY_ALIAS_MAP:
        return KEY_ALIAS_MAP[low]

    # Decimal VK code support when formatted as integer >= 8 (e.g., 115 -> F4, 120 -> F9, 45 -> Insert)
    if cleaned.isdigit():
        val_int = int(cleaned)
        if val_int == 0:
            return None
        if val_int >= 8 and val_int in VK_CODE_MAP:
            return VK_CODE_MAP[val_int]

    return None


def normalize_chord(key: str | None, modifier: str | None = None) -> str:
    """Format a key and optional modifier into a deterministic canonical chord (e.g. 'Shift+F9' or 'F4')."""
    raw_tokens: list[str] = []

    for part in (modifier, key):
        if part is None:
            continue
        cleaned = _strip_inline_comment(str(part))
        if not cleaned:
            continue
        # Split composite chord strings such as "LeftShift+F9", "Ctrl + F4", "LShiftKey | F9", or "LeftShift, F9"
        for sub in re.split(r"[+|,\s]+", cleaned):
            sub_clean = sub.strip()
            if sub_clean:
                raw_tokens.append(sub_clean)

    modifiers_found: list[str] = []
    primary_key: str | None = None

    for tok in raw_tokens:
        norm = normalize_key_name(tok)
        if norm is None:
            continue
        if norm in CANONICAL_MODIFIERS:
            if norm not in modifiers_found:
                modifiers_found.append(norm)
        else:
            primary_key = norm

    ordered_mods = [m for m in CANONICAL_MODIFIERS if m in modifiers_found]

    if primary_key is not None:
        if ordered_mods:
            return "+".join([*ordered_mods, primary_key])
        return primary_key

    if ordered_mods:
        return "+".join(ordered_mods)

    return ""


def _split_canonical_chord(chord: str) -> tuple[str | None, str | None]:
    """Split a canonical chord like 'Shift+F9' into (modifier_part_or_None, base_key_or_None)."""
    if not chord:
        return None, None
    parts = [p for p in chord.split("+") if p]
    if not parts:
        return None, None
    mods = [p for p in parts[:-1] if p in CANONICAL_MODIFIERS]
    base = parts[-1]
    if base in CANONICAL_MODIFIERS and not mods:
        return None, base
    mod_str = "+".join(mods) if mods else None
    return mod_str, base


def _rel_posix(path: Path, base_dir: Path) -> str:
    """Compute portable relative POSIX path within game_dir without leaking host absolute paths."""
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except Exception:
        try:
            return path.relative_to(base_dir).as_posix()
        except Exception:
            return path.name


def _infer_owner_mod(rel_path: str) -> str:
    """Infer canonical owner_mod name from relative path within the profile directory."""
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    # Strip GTA5-Profiles/Inactive/<ProfileName>/ prefix if present so owner_mod reflects the mod itself
    if len(parts) >= 3 and parts[0].lower() == "gta5-profiles" and parts[1].lower() == "inactive":
        parts = parts[3:]

    if not parts:
        return "UnknownMod"

    filename = parts[-1]
    stem = Path(filename).stem
    stem_low = stem.lower()

    if stem_low == "ragepluginhook":
        return "RAGEPluginHook"
    if stem_low in {"scripthookvdotnet", "scripthookvdotnet2", "scripthookvdotnet3"}:
        return "ScriptHookVDotNet"
    if stem_low in {"trainerv", "simpletrainer"}:
        return "SimpleTrainer"
    if stem_low == "menyoo":
        return "Menyoo"

    if len(parts) >= 2 and parts[0].lower() == "lspdfr":
        return "LSPDFR"

    if len(parts) >= 3 and parts[0].lower() == "plugins" and parts[1].lower() == "lspdfr":
        if len(parts) >= 4:
            return parts[2]
        return stem

    if stem_low.endswith("config") and len(stem) > 6:
        return stem[:-6]

    return stem


def _infer_context_scope(
    rel_path: str,
    owner_mod: str,
    section: str,
    setting_name: str,
    canonical_key: str,
) -> str:
    """Classify a keybind into one of: global_loader, on_duty_police, in_vehicle, mod_menu, controller."""
    sec_low = section.lower()
    set_low = setting_name.lower()
    owner_low = owner_mod.lower()
    path_low = rel_path.replace("\\", "/").lower()

    # 1. Controller scope
    if (
        canonical_key in CONTROLLER_BUTTON_KEYS
        or any(tok in sec_low for tok in ("controller", "gamepad", "joystick", "xbox", "pad"))
        or any(tok in set_low for tok in ("controller", "gamepad", "dpad", "button"))
        and canonical_key in {"A", "B", "X", "Y", *CONTROLLER_BUTTON_KEYS}
        and "controller" in (sec_low + set_low)
    ):
        return "controller"

    # 2. Global loader scope (RPH console, SHVDN reload)
    if (
        owner_low in {"ragepluginhook", "scripthookvdotnet", "scripthookv"}
        or set_low in {"consolekey", "reloadkey"}
        or "consolekey" in set_low
        or "reloadkey" in set_low
    ):
        return "global_loader"

    # 3. Vehicle / horn / siren scope
    if any(
        tok in set_low or tok in sec_low
        for tok in (
            "siren",
            "horn",
            "indicator",
            "turnsignal",
            "seatbelt",
            "headlight",
            "cruise",
            "els_",
        )
    ):
        return "in_vehicle"

    # 4. On-duty police gameplay actions (Backup, Callout, TrafficStop, Arrest, etc.)
    police_action_tokens = (
        "backup",
        "callout",
        "arrest",
        "patrol",
        "duty",
        "dispatch",
        "pullover",
        "trafficstop",
        "holster",
        "intimidate",
        "frisk",
        "cuff",
        "taser",
        "radar",
        "coroner",
        "breathalyzer",
        "interaction_menu",
        "backup_menu",
        "chase",
        "pursuit",
    )
    if any(tok in set_low for tok in police_action_tokens):
        return "on_duty_police"

    # 5. Top-level Mod Menu activation hotkeys
    if any(
        tok in set_low
        for tok in (
            "menukey",
            "openmenukey",
            "mainmenukey",
            "togglemenukey",
            "modmenukey",
            "activationkey",
            "activation_key",
            "openkey",
        )
    ):
        return "mod_menu"

    # 6. Remaining LSPDFR / plugins/LSPDFR settings default to on_duty_police
    if (
        "/lspdfr/" in f"/{path_low}"
        or owner_low in {"lspdfr", "policingredefined", "stoptheped", "ultimatebackup", "compulite", "grammarpolice"}
    ):
        return "on_duty_police"

    return "mod_menu"


_KEY_SETTING_KEYWORDS = (
    "key",
    "button",
    "hotkey",
    "menu",
    "console",
    "reload",
    "shortcut",
    "bind",
    "toggle",
)

_NON_KEY_SETTING_SUFFIXES = (
    "title",
    "name",
    "width",
    "height",
    "size",
    "count",
    "time",
    "timeout",
    "delay",
    "duration",
    "speed",
    "scale",
    "volume",
    "pitch",
    "opacity",
    "alpha",
    "color",
    "colour",
    "red",
    "green",
    "blue",
    "_x",
    "_y",
    "_z",
    "posx",
    "posy",
    "posz",
    "offsetx",
    "offsety",
    "offsetz",
    "distance",
    "radius",
    "chance",
    "probability",
    "enabled",
    "enable",
    "disable",
    "disabled",
    "path",
    "file",
    "folder",
    "url",
    "version",
    "author",
    "description",
    "log",
    "sound",
    "audio",
    "Position",
)


def _is_modifier_setting_name(setting_name: str) -> bool:
    """Return True if an INI/XML setting name represents a companion modifier key rather than a primary key."""
    low = setting_name.lower().strip()
    return (
        "modifier" in low
        or low in {"modkey", "shiftkey", "ctrlkey", "altkey"}
        or low.endswith("modifier")
        or low.endswith("modifierkey")
    )


def _is_candidate_key_setting(setting_name: str, section_name: str, raw_val: str) -> bool:
    """Determine if an INI key=value pair is a keybind assignment rather than a numeric/boolean/text parameter."""
    set_low = setting_name.lower().strip()
    sec_low = section_name.lower().strip()
    val_clean = _strip_inline_comment(raw_val)

    if not set_low or not val_clean:
        return False

    if _is_modifier_setting_name(set_low):
        return False

    explicit_key_suffix = set_low.endswith(("key", "hotkey", "keybind", "button", "shortcut"))
    if not explicit_key_suffix and any(
        set_low.endswith(sfx.lower()) for sfx in _NON_KEY_SETTING_SUFFIXES
    ):
        return False

    # Exclude pure decimal numbers unless it's hex 0x... or a single digit on an explicit *Key setting
    if val_clean.isdigit() and len(val_clean) > 1:
        if "key" not in set_low and "hotkey" not in set_low:
            return False

    in_keys_section = any(
        k in sec_low for k in ("key", "control", "bind", "shortcut", "hotkey", "input")
    )
    has_key_word = any(kw in set_low for kw in _KEY_SETTING_KEYWORDS)

    if not (has_key_word or in_keys_section):
        return False

    chord = normalize_chord(val_clean)
    if not chord:
        return False

    _, base_key = _split_canonical_chord(chord)
    return base_key in VALID_CANONICAL_KEYS


def _strip_key_suffix(setting_name: str) -> str:
    """Extract logical prefix of a key setting (e.g. 'MenuKey' -> 'menu', 'OpenMenuHotkey' -> 'openmenu')."""
    low = setting_name.lower().strip()
    for sfx in ("hotkey", "keybind", "button", "key"):
        if low.endswith(sfx) and len(low) > len(sfx):
            return low[: -len(sfx)].rstrip("_")
    return low


def _strip_modifier_suffix(setting_name: str) -> str:
    """Extract logical prefix of a modifier setting (e.g. 'MenuModifierKey' -> 'menu', 'ModifierKey' -> '')."""
    low = setting_name.lower().strip()
    for sfx in ("modifierhotkey", "modifierkey", "modifierbutton", "modifier", "modkey"):
        if low == sfx:
            return ""
        if low.endswith(sfx):
            return low[: -len(sfx)].rstrip("_")
    return ""


def _resolve_companion_modifier(
    key_setting: str,
    key_line: int,
    all_key_entries: list[tuple[int, str, str]],
    mod_entries: list[tuple[int, str, str]],
) -> str | None:
    """Match a key setting with its companion *Modifier* setting in the same INI section."""
    if not mod_entries:
        return None

    key_prefix = _strip_key_suffix(key_setting)

    # 1. Exact prefix match (e.g. MenuKey <-> MenuModifierKey / MenuModifier, BackupKey <-> BackupModifierKey)
    for _m_line, m_name, m_val in mod_entries:
        mod_prefix = _strip_modifier_suffix(m_name)
        if mod_prefix and key_prefix and mod_prefix == key_prefix:
            return m_val

    # 2. Generic section-level ModifierKey / Modifier (mod_prefix == "")
    generic_mods = [
        (m_line, m_name, m_val)
        for (m_line, m_name, m_val) in mod_entries
        if _strip_modifier_suffix(m_name) == ""
    ]
    if not generic_mods:
        return None

    # If there is only one keybind in the entire section, generic ModifierKey applies to it
    if len(all_key_entries) == 1:
        return generic_mods[0][2]

    # When multiple keys exist in the same section (e.g. MenuKey=F9, ModifierKey=LeftShift, BackupKey=B):
    # A generic ModifierKey applies to the immediately preceding keybind before ModifierKey,
    # or to primary menu/activation keys (MenuKey, OpenKey, ActivationKey, MainKey, ToggleKey, Key, Hotkey)
    for m_line, _m_name, m_val in generic_mods:
        preceding_keys = [k for k in all_key_entries if k[0] < m_line]
        if preceding_keys and preceding_keys[-1][0] == key_line and preceding_keys[-1][1] == key_setting:
            return m_val

    if key_prefix in {"menu", "openmenu", "mainmenu", "togglemenu", "open", "activation", "main", "key", "hotkey", ""}:
        return generic_mods[0][2]

    return None


def _parse_ini_or_cfg_file(
    file_path: Path,
    rel_path: str,
    profile_label: str,
) -> list[dict[str, Any]]:
    """Parse an .ini or .cfg file for keybind and modifier assignments with line numbers and sections."""
    try:
        if file_path.stat().st_size > MAX_CONFIG_FILE_BYTES:
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    owner_mod = _infer_owner_mod(rel_path)
    section = "root"
    section_order: list[str] = ["root"]
    section_lines: dict[str, list[tuple[int, str, str]]] = {"root": []}

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith((";", "#", "//")):
            continue
        if stripped.startswith("[") and "]" in stripped:
            section = stripped[1 : stripped.index("]")].strip() or "root"
            if section not in section_lines:
                section_order.append(section)
                section_lines[section] = []
            continue
        if "=" in stripped:
            k_part, v_part = stripped.split("=", 1)
            k_clean = k_part.strip()
            v_clean = _strip_inline_comment(v_part)
            if k_clean and v_clean:
                section_lines[section].append((line_no, k_clean, v_clean))

    bindings: list[dict[str, Any]] = []

    for sec_name in section_order:
        entries = section_lines.get(sec_name, [])
        if not entries:
            continue

        mod_entries: list[tuple[int, str, str]] = []
        key_entries: list[tuple[int, str, str]] = []

        for line_no, k_name, v_val in entries:
            if _is_modifier_setting_name(k_name):
                mod_entries.append((line_no, k_name, v_val))
            elif _is_candidate_key_setting(k_name, sec_name, v_val):
                key_entries.append((line_no, k_name, v_val))

        for line_no, k_name, v_val in key_entries:
            companion_mod_raw = _resolve_companion_modifier(
                k_name, line_no, key_entries, mod_entries
            )
            canonical_chord = normalize_chord(v_val, companion_mod_raw)
            if not canonical_chord:
                continue
            canonical_mod, canonical_key = _split_canonical_chord(canonical_chord)
            if not canonical_key or canonical_key not in VALID_CANONICAL_KEYS:
                continue

            context_scope = _infer_context_scope(
                rel_path=rel_path,
                owner_mod=owner_mod,
                section=sec_name,
                setting_name=k_name,
                canonical_key=canonical_key,
            )

            bindings.append(
                {
                    "relative_path": rel_path,
                    "file": rel_path,
                    "line": line_no,
                    "section": sec_name,
                    "setting_name": k_name,
                    "raw_value": v_val,
                    "modifier_raw": companion_mod_raw,
                    "canonical_key": canonical_key,
                    "canonical_modifier": canonical_mod,
                    "canonical_chord": canonical_chord,
                    "owner_mod": owner_mod,
                    "profile": profile_label,
                    "context_scope": context_scope,
                }
            )

    return bindings


def _find_line_number(text: str, needle: str, start_line: int = 1) -> int:
    """Locate 1-indexed line number containing needle."""
    for idx, line in enumerate(text.splitlines(), start=1):
        if idx >= start_line and needle in line:
            return idx
    return 1


def _parse_xml_file(
    file_path: Path,
    rel_path: str,
    profile_label: str,
) -> list[dict[str, Any]]:
    """Parse an .xml configuration file for <Key>/<ModifierKey> elements or keybind attributes."""
    try:
        if file_path.stat().st_size > MAX_CONFIG_FILE_BYTES:
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    owner_mod = _infer_owner_mod(rel_path)
    bindings: list[dict[str, Any]] = []

    try:
        root_elem = ET.fromstring(text)
    except Exception:
        return []

    for parent in root_elem.iter():
        parent_tag = parent.tag.split("}")[-1]

        # 1. Check attributes on element (e.g. <Bind Key="F9" Modifier="LeftShift" />)
        if parent.attrib:
            attr_mods: list[tuple[int, str, str]] = []
            attr_keys: list[tuple[int, str, str]] = []
            for idx, (attr_k, attr_v) in enumerate(parent.attrib.items()):
                if _is_modifier_setting_name(attr_k):
                    attr_mods.append((idx, attr_k, attr_v))
                elif _is_candidate_key_setting(attr_k, parent_tag, attr_v):
                    attr_keys.append((idx, attr_k, attr_v))

            for idx, attr_k, attr_v in attr_keys:
                comp_mod = _resolve_companion_modifier(attr_k, idx, attr_keys, attr_mods)
                chord = normalize_chord(attr_v, comp_mod)
                if not chord:
                    continue
                c_mod, c_key = _split_canonical_chord(chord)
                if not c_key or c_key not in VALID_CANONICAL_KEYS:
                    continue
                line_no = _find_line_number(text, attr_v)
                scope = _infer_context_scope(rel_path, owner_mod, parent_tag, attr_k, c_key)
                bindings.append(
                    {
                        "relative_path": rel_path,
                        "file": rel_path,
                        "line": line_no,
                        "section": parent_tag,
                        "setting_name": attr_k,
                        "raw_value": attr_v,
                        "modifier_raw": comp_mod,
                        "canonical_key": c_key,
                        "canonical_modifier": c_mod,
                        "canonical_chord": chord,
                        "owner_mod": owner_mod,
                        "profile": profile_label,
                        "context_scope": scope,
                    }
                )

        # 2. Check child elements inside parent (e.g. <Key>F9</Key><ModifierKey>LeftShift</ModifierKey>)
        children = list(parent)
        if not children:
            continue

        child_mods: list[tuple[int, str, str]] = []
        child_keys: list[tuple[int, str, str]] = []
        for idx, child in enumerate(children):
            c_tag = child.tag.split("}")[-1]
            c_text = (child.text or "").strip()
            if not c_text:
                continue
            if _is_modifier_setting_name(c_tag):
                child_mods.append((idx, c_tag, c_text))
            elif _is_candidate_key_setting(c_tag, parent_tag, c_text):
                child_keys.append((idx, c_tag, c_text))

        for idx, c_tag, c_text in child_keys:
            comp_mod = _resolve_companion_modifier(c_tag, idx, child_keys, child_mods)
            chord = normalize_chord(c_text, comp_mod)
            if not chord:
                continue
            c_mod, c_key = _split_canonical_chord(chord)
            if not c_key or c_key not in VALID_CANONICAL_KEYS:
                continue
            line_no = _find_line_number(text, c_text)
            scope = _infer_context_scope(rel_path, owner_mod, parent_tag, c_tag, c_key)
            bindings.append(
                {
                    "relative_path": rel_path,
                    "file": rel_path,
                    "line": line_no,
                    "section": parent_tag,
                    "setting_name": c_tag,
                    "raw_value": c_text,
                    "modifier_raw": comp_mod,
                    "canonical_key": c_key,
                    "canonical_modifier": c_mod,
                    "canonical_chord": chord,
                    "owner_mod": owner_mod,
                    "profile": profile_label,
                    "context_scope": scope,
                }
            )

    return bindings


def _parse_json_config_file(
    file_path: Path,
    rel_path: str,
    profile_label: str,
) -> list[dict[str, Any]]:
    """Parse GTA-Anything *Config.json (and mod JSON configs) for inputs.activation_key / modifier_key."""
    try:
        if file_path.stat().st_size > MAX_CONFIG_FILE_BYTES:
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except Exception:
        return []

    if not isinstance(data, dict):
        return []

    owner_mod = str(
        data.get("mod_id")
        or (data.get("meta", {}) if isinstance(data.get("meta"), dict) else {}).get("id")
        or _infer_owner_mod(rel_path)
    )
    bindings: list[dict[str, Any]] = []

    # 1. Check "inputs" block (standard GTA-Anything *Config.json / gameplay_ir.json format)
    inputs_block = data.get("inputs")
    if isinstance(inputs_block, dict):
        act_raw = inputs_block.get("activation_key") or inputs_block.get("ActivationKey")
        mod_raw = inputs_block.get("modifier_key") or inputs_block.get("ModifierKey")
        if act_raw:
            chord = normalize_chord(str(act_raw), str(mod_raw) if mod_raw else None)
            if chord:
                c_mod, c_key = _split_canonical_chord(chord)
                if c_key and c_key in VALID_CANONICAL_KEYS:
                    line_no = _find_line_number(text, str(act_raw))
                    bindings.append(
                        {
                            "relative_path": rel_path,
                            "file": rel_path,
                            "line": line_no,
                            "section": "inputs",
                            "setting_name": "activation_key",
                            "raw_value": str(act_raw),
                            "modifier_raw": str(mod_raw) if mod_raw else None,
                            "canonical_key": c_key,
                            "canonical_modifier": c_mod,
                            "canonical_chord": chord,
                            "owner_mod": owner_mod,
                            "profile": profile_label,
                            "context_scope": "mod_menu",
                        }
                    )

    # 2. Check top-level activation_key / ActivationKey / Hotkey if not under inputs
    if not bindings:
        act_top = (
            data.get("activation_key")
            or data.get("ActivationKey")
            or data.get("MenuKey")
            or data.get("Hotkey")
            or data.get("hotkey")
        )
        mod_top = data.get("modifier_key") or data.get("ModifierKey")
        if act_top and isinstance(act_top, str):
            chord = normalize_chord(act_top, str(mod_top) if mod_top else None)
            if chord:
                c_mod, c_key = _split_canonical_chord(chord)
                if c_key and c_key in VALID_CANONICAL_KEYS:
                    line_no = _find_line_number(text, act_top)
                    bindings.append(
                        {
                            "relative_path": rel_path,
                            "file": rel_path,
                            "line": line_no,
                            "section": "root",
                            "setting_name": "activation_key",
                            "raw_value": act_top,
                            "modifier_raw": str(mod_top) if mod_top else None,
                            "canonical_key": c_key,
                            "canonical_modifier": c_mod,
                            "canonical_chord": chord,
                            "owner_mod": owner_mod,
                            "profile": profile_label,
                            "context_scope": "mod_menu",
                        }
                    )

    return bindings


def _collect_profile_config_files(profile_root: Path) -> list[Path]:
    """Collect candidate .ini, .cfg, .xml, and *Config.json files across root, scripts/, plugins/, and lspdfr/."""
    collected: list[Path] = []
    seen: set[Path] = set()

    # 1. Root-level .ini, .cfg, and *Config.json files
    try:
        for item in sorted(profile_root.iterdir()):
            if not item.is_file():
                continue
            ext = item.suffix.lower()
            if ext in BINARY_OR_IGNORED_EXTENSIONS:
                continue
            if ext in {".ini", ".cfg"} or item.name.lower().endswith("config.json"):
                collected.append(item)
                seen.add(item)
    except Exception:
        pass

    # 2. Recursive scan inside scripts/, plugins/, and lspdfr/
    for sub_name in ("scripts", "plugins", "lspdfr"):
        sub_dir = profile_root / sub_name
        if not sub_dir.exists() or not sub_dir.is_dir():
            continue
        try:
            for item in sorted(sub_dir.rglob("*")):
                if not item.is_file() or item in seen:
                    continue
                ext = item.suffix.lower()
                if ext in BINARY_OR_IGNORED_EXTENSIONS:
                    continue
                name_low = item.name.lower()
                if ext in {".ini", ".cfg", ".xml"} or (
                    ext == ".json" and ("config" in name_low or "key" in name_low or "input" in name_low)
                ):
                    collected.append(item)
                    seen.add(item)
        except Exception:
            pass

    return collected


def scan_installed_keybinds(
    game_dir: str | Path,
    include_inactive_profiles: bool = True,
) -> dict[str, Any]:
    """Read-only scan of <game_dir> and <game_dir>/GTA5-Profiles/Inactive/* for installed keybind assignments."""
    root = Path(game_dir)
    if not root.exists() or not root.is_dir():
        return {
            "ok": False,
            "active_profile_mode": None,
            "profiles_scanned": [],
            "scanned_files": [],
            "bindings": [],
            "occupied_active_chords": [],
            "occupied_all_chords": [],
            "summary": {
                "total_bindings": 0,
                "active_bindings": 0,
                "inactive_bindings": 0,
                "scanned_file_count": 0,
            },
        }

    active_profile_mode: str | None = None
    active_mode_path = root / "GTA5-Profiles" / "ActiveMode.txt"
    if active_mode_path.exists() and active_mode_path.is_file():
        try:
            mode_txt = active_mode_path.read_text(encoding="utf-8", errors="replace").strip()
            if mode_txt:
                active_profile_mode = mode_txt.splitlines()[0].strip()
        except Exception:
            pass

    profile_targets: list[tuple[str, Path]] = [("active", root)]
    if include_inactive_profiles:
        inactive_dir = root / "GTA5-Profiles" / "Inactive"
        if inactive_dir.exists() and inactive_dir.is_dir():
            try:
                for child in sorted(inactive_dir.iterdir()):
                    if child.is_dir():
                        profile_targets.append((f"inactive:{child.name}", child))
            except Exception:
                pass

    profiles_scanned: list[str] = []
    scanned_files: list[str] = []
    bindings: list[dict[str, Any]] = []

    for profile_label, prof_root in profile_targets:
        profiles_scanned.append(profile_label)
        candidate_files = _collect_profile_config_files(prof_root)
        for file_path in candidate_files:
            rel_path = _rel_posix(file_path, root)
            scanned_files.append(rel_path)
            ext = file_path.suffix.lower()
            if ext in {".ini", ".cfg"}:
                bindings.extend(_parse_ini_or_cfg_file(file_path, rel_path, profile_label))
            elif ext == ".xml":
                bindings.extend(_parse_xml_file(file_path, rel_path, profile_label))
            elif ext == ".json":
                bindings.extend(_parse_json_config_file(file_path, rel_path, profile_label))

    active_bindings = [b for b in bindings if b["profile"] == "active"]
    inactive_bindings = [b for b in bindings if b["profile"] != "active"]

    occupied_active_chords = sorted({b["canonical_chord"] for b in active_bindings if b["canonical_chord"]})
    occupied_all_chords = sorted({b["canonical_chord"] for b in bindings if b["canonical_chord"]})

    return {
        "ok": True,
        "active_profile_mode": active_profile_mode,
        "profiles_scanned": profiles_scanned,
        "scanned_files": scanned_files,
        "bindings": bindings,
        "occupied_active_chords": occupied_active_chords,
        "occupied_all_chords": occupied_all_chords,
        "summary": {
            "total_bindings": len(bindings),
            "active_bindings": len(active_bindings),
            "inactive_bindings": len(inactive_bindings),
            "scanned_file_count": len(scanned_files),
        },
    }


def evaluate_keybind_conflicts(
    activation_key: str,
    modifier_key: str | None = None,
    scanned_registry: dict[str, Any] | None = None,
    loader_target: str = "shvdn_enhanced",
    target_profile: str = "active",
) -> dict[str, Any]:
    """Evaluate requested keybind chord against baseline loader/gameplay keys and dynamic scanned_registry."""
    req_chord = normalize_chord(activation_key, modifier_key)
    req_mod, req_base = _split_canonical_chord(req_chord)

    conflicts: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str, str, str]] = set()

    bindings: list[dict[str, Any]] = []
    if isinstance(scanned_registry, dict):
        raw_list = scanned_registry.get("bindings", [])
        if isinstance(raw_list, list):
            bindings = raw_list

    # Detect whether LSPDFR / police bindings are parked in an inactive profile
    has_inactive_lspdfr = any(
        str(b.get("profile", "")).lower().startswith("inactive:lspdfr")
        or (
            str(b.get("profile", "")).startswith("inactive:")
            and b.get("context_scope") == "on_duty_police"
        )
        for b in bindings
    )
    has_active_lspdfr = any(
        b.get("profile") == "active" and b.get("context_scope") == "on_duty_police"
        for b in bindings
    )

    # 1. Evaluate dynamic entries from scanned_registry first (concrete file/line provenance)
    if req_chord and req_base:
        for entry in bindings:
            entry_chord = str(entry.get("canonical_chord", ""))
            if not entry_chord:
                continue
            entry_mod, entry_base = _split_canonical_chord(entry_chord)
            if not entry_base or entry_base != req_base:
                continue

            entry_profile = str(entry.get("profile", "active"))
            entry_scope = str(entry.get("context_scope", "mod_menu"))
            entry_owner = str(entry.get("owner_mod", "UnknownMod"))
            entry_rel_path = str(entry.get("relative_path", entry.get("file", "")))
            entry_line = entry.get("line")
            entry_sec = entry.get("section")
            entry_setting = entry.get("setting_name")

            exact_chord_match = entry_chord == req_chord
            one_modified_one_not = (bool(req_mod) != bool(entry_mod)) and (req_base == entry_base)

            if not (exact_chord_match or one_modified_one_not):
                continue

            severity: str
            match_type: str
            resolution: str
            reason: str
            suggestion: str

            # Determine severity according to profile, exact vs bleed match, and loader/scope
            if entry_profile.startswith("inactive:"):
                severity = "INACTIVE_PROFILE_INFO"
                match_type = "INACTIVE_PROFILE"
                resolution = "CLEAR_WHEN_ISOLATED"
                reason = (
                    f"Chord '{req_chord}' overlaps with '{entry_chord}' ({entry_owner} "
                    f"{entry_setting or ''} in {entry_rel_path}:{entry_line}), which is currently "
                    f"parked in '{entry_profile}' (CLEAR_WHEN_ISOLATED)."
                )
                suggestion = (
                    f"Safe while '{entry_profile}' remains parked; rebind if you intend to merge both profiles."
                )
            elif exact_chord_match:
                if (
                    target_profile != "active"
                    and target_profile != entry_profile
                    and entry_scope == "on_duty_police"
                    and loader_target.startswith("shvdn")
                ):
                    severity = "INACTIVE_PROFILE_INFO"
                    match_type = "INACTIVE_PROFILE"
                    resolution = "CLEAR_WHEN_ISOLATED"
                    reason = (
                        f"Chord '{req_chord}' matches on-duty police binding '{entry_chord}' in "
                        f"{entry_rel_path}:{entry_line}, which will be isolated when deployed to '{target_profile}'."
                    )
                    suggestion = "Deploy into the isolated target profile via `gta-anything profile switch`."
                else:
                    severity = "BLOCKING"
                    match_type = "EXACT_CHORD"
                    resolution = "REBIND_REQUIRED"
                    reason = (
                        f"Exact keybind collision on '{req_chord}' with active {entry_owner} setting "
                        f"'{entry_setting}' in {entry_rel_path}:{entry_line} (scope={entry_scope})."
                    )
                    suggestion = (
                        "Rebind to a conflict-free chord using `gta-anything conflict-check --auto-rebind`."
                    )
            else:
                # Base key match where one has a modifier and the other doesn't -> CONTEXT_WARNING
                severity = "CONTEXT_WARNING"
                match_type = "BASE_KEY_BLEED"
                resolution = "SUPPRESS_BASE_KEY_OR_REBIND"
                reason = (
                    f"Base-key chord bleed on '{req_base}': requested '{req_chord}' shares base key "
                    f"with '{entry_chord}' ({entry_owner} '{entry_setting}' in {entry_rel_path}:{entry_line}). "
                    "Pressing the modified chord can trigger unmodified key listeners unless input suppression is active."
                )
                suggestion = (
                    f"Choose a base key not bound by {entry_owner} (e.g. via `recommend_safe_chords`) "
                    "or suppress the base key during menu activation."
                )

            sig = (entry_chord, entry_owner.lower(), entry_profile, match_type)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                conflicts.append(
                    {
                        "severity": severity,
                        "match_type": match_type,
                        "requested_chord": req_chord,
                        "conflicting_chord": entry_chord,
                        "canonical_chord": entry_chord,
                        "owner_mod": entry_owner,
                        "relative_path": entry_rel_path,
                        "file": entry_rel_path,
                        "line": entry_line,
                        "section": entry_sec,
                        "setting_name": entry_setting,
                        "profile": entry_profile,
                        "context_scope": entry_scope,
                        "resolution": resolution,
                        "reason": reason,
                        "message": reason,
                        "suggestion": suggestion,
                    }
                )

    # 2. Evaluate against built-in baseline conflict knowledge base
    if req_chord and req_base:
        for base_item in BASELINE_KEYBIND_KNOWLEDGE_BASE:
            kb_chord = str(base_item["canonical_chord"])
            kb_key = str(base_item["canonical_key"])
            kb_mod = base_item["canonical_modifier"]
            kb_owner = str(base_item["owner_mod"])
            kb_scope = str(base_item["context_scope"])
            kb_setting = str(base_item["setting_name"])

            if kb_key != req_base:
                continue

            exact_match = kb_chord == req_chord
            one_mod_one_not = (bool(req_mod) != bool(kb_mod)) and (kb_key == req_base)
            if not (exact_match or one_mod_one_not):
                continue

            # Skip redundant baseline entry if an active dynamic binding already reported the exact same chord & scope/owner
            already_covered = any(
                c["conflicting_chord"] == kb_chord
                and (
                    c["owner_mod"].lower() == kb_owner.lower()
                    or (kb_scope == "on_duty_police" and c["context_scope"] == "on_duty_police")
                    or (kb_scope == "global_loader" and c["context_scope"] == "global_loader")
                )
                for c in conflicts
            )
            if already_covered:
                continue

            if exact_match:
                if kb_scope == "global_loader":
                    severity = "BLOCKING"
                    match_type = "EXACT_CHORD"
                    resolution = "REBIND_REQUIRED"
                    reason = f"Exact collision on global loader key '{kb_chord}' ({kb_owner}: {base_item['reason']})"
                elif kb_scope == "on_duty_police":
                    if loader_target.startswith("shvdn"):
                        if has_inactive_lspdfr and not has_active_lspdfr:
                            severity = "INACTIVE_PROFILE_INFO"
                            match_type = "INACTIVE_PROFILE"
                            resolution = "CLEAR_WHEN_ISOLATED"
                            reason = (
                                f"Key '{kb_chord}' is reserved by {kb_owner} (on_duty_police), "
                                "which is currently parked in inactive:LSPDFR (CLEAR_WHEN_ISOLATED)."
                            )
                        else:
                            severity = "CONTEXT_WARNING"
                            match_type = "BASELINE_KNOWLEDGE"
                            resolution = "ISOLATE_OR_REBIND"
                            reason = (
                                f"Key '{kb_chord}' collides with {kb_owner} on_duty_police keybind "
                                f"({base_item['reason']}) when merging SHVDN scripts into an active RPH directory."
                            )
                    else:
                        severity = "BLOCKING"
                        match_type = "EXACT_CHORD"
                        resolution = "REBIND_REQUIRED"
                        reason = f"Exact collision with {kb_owner} on-duty hotkey '{kb_chord}' ({base_item['reason']})."
                else:
                    severity = "BLOCKING"
                    match_type = "EXACT_CHORD"
                    resolution = "REBIND_REQUIRED"
                    reason = f"Exact collision with baseline {kb_owner} key '{kb_chord}': {base_item['reason']}"
            else:
                # Base-key match where one has a modifier and the other does not (e.g. Shift+E vs vanilla E horn, Shift+F4 vs RPH F4)
                if kb_scope in {"in_vehicle", "global_loader"}:
                    severity = "CONTEXT_WARNING"
                    match_type = "BASE_KEY_BLEED"
                    resolution = "SUPPRESS_BASE_KEY_OR_REBIND"
                    reason = (
                        f"Chord bleed warning on base key '{kb_key}': '{req_chord}' shares base key "
                        f"with {kb_owner} '{kb_chord}' ({base_item['reason']}). Pressing '{req_chord}' "
                        f"will also trigger '{kb_chord}' unless game control input is suppressed."
                    )
                else:
                    # Modified function/letter key (e.g. Shift+F3 or Ctrl+B) against baseline trainer/LSPDFR single key is safe
                    continue

            conflicts.append(
                {
                    "severity": severity,
                    "match_type": match_type,
                    "requested_chord": req_chord,
                    "conflicting_chord": kb_chord,
                    "canonical_chord": kb_chord,
                    "owner_mod": kb_owner,
                    "relative_path": "builtin:baseline",
                    "file": "builtin:baseline",
                    "line": None,
                    "section": "baseline",
                    "setting_name": kb_setting,
                    "profile": "builtin",
                    "context_scope": kb_scope,
                    "resolution": resolution,
                    "reason": reason,
                    "message": reason,
                    "suggestion": str(base_item["suggestion"]),
                }
            )

    blocking_count = sum(1 for c in conflicts if c["severity"] == "BLOCKING")
    context_warning_count = sum(1 for c in conflicts if c["severity"] == "CONTEXT_WARNING")
    inactive_info_count = sum(1 for c in conflicts if c["severity"] == "INACTIVE_PROFILE_INFO")

    return {
        "ok": blocking_count == 0,
        "has_conflicts": (blocking_count + context_warning_count) > 0,
        "requested_activation_key": activation_key,
        "requested_modifier_key": modifier_key,
        "requested_chord": req_chord,
        "canonical_chord": req_chord,
        "loader_target": loader_target,
        "target_profile": target_profile,
        "conflicts": conflicts,
        "findings": conflicts,
        "blocking_count": blocking_count,
        "context_warning_count": context_warning_count,
        "inactive_info_count": inactive_info_count,
    }


def recommend_safe_chords(
    scanned_registry: dict[str, Any] | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    """Deterministically score and return the Top `count` zero-conflict candidate chords."""
    if count <= 0:
        return []

    bindings: list[dict[str, Any]] = []
    if isinstance(scanned_registry, dict):
        raw_list = scanned_registry.get("bindings", [])
        if isinstance(raw_list, list):
            bindings = raw_list

    active_chords = {
        str(b.get("canonical_chord", ""))
        for b in bindings
        if b.get("profile") == "active" and b.get("canonical_chord")
    }
    all_chords = {
        str(b.get("canonical_chord", ""))
        for b in bindings
        if b.get("canonical_chord")
    }
    active_base_keys = {
        str(b.get("canonical_key", ""))
        for b in bindings
        if b.get("profile") == "active" and b.get("canonical_key")
    }

    scored_candidates: list[tuple[int, int, dict[str, Any]]] = []

    for idx, (act_key, mod_key, base_reason) in enumerate(CANDIDATE_SAFE_CHORDS):
        canonical = normalize_chord(act_key, mod_key)
        if not canonical or canonical in active_chords:
            continue

        eval_res = evaluate_keybind_conflicts(
            activation_key=act_key,
            modifier_key=mod_key,
            scanned_registry=scanned_registry,
        )
        if eval_res["blocking_count"] > 0 or eval_res["context_warning_count"] > 0:
            continue

        # Deterministic quality score:
        # +100 base score for 0 BLOCKING & 0 CONTEXT_WARNING
        # +20 if also completely free across all inactive profiles
        # +15 if base function key is not used by any active binding at all
        # +10 if chord uses an explicit modifier (Shift/Ctrl/Alt) to prevent single-key accidental presses
        score = 100
        if canonical not in all_chords:
            score += 20
        if act_key not in active_base_keys:
            score += 15
        if mod_key is not None:
            score += 10

        scored_candidates.append(
            (
                -score,
                idx,
                {
                    "activation_key": act_key,
                    "modifier_key": mod_key,
                    "canonical_chord": canonical,
                    "score": score,
                    "reason": base_reason,
                },
            )
        )

    scored_candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored_candidates[:count]]
