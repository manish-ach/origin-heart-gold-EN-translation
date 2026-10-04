"""Read-only provenance checks for paired runtime QA; these do not make RTC deterministic."""
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import re
import stat
import sys


REQUIRED_INPUTS = ("checker", "manifest", "rom_zh", "rom_en")
PACKAGES = ("py-desmume", "Pillow", "capstone", "ndspy")
KNOWN_SETTINGS = {"backup_import_bytes": 524288, "reset_after_import": True,
                  "cycle_with_joystick": False,
                  "other_native_settings": "library defaults; not queried"}
CLOCK = {"source": "host RTC", "controlled": False,
         "limitation": "Clock-dependent behavior and encounters are not deterministic"}


def capture_inputs(paths):
    """Hash each named input, retaining errors rather than misclassifying them as game bugs.

    fstat brackets detect replacement/change while hashing. Whole-run before/after
    hashes detect persistent input changes, not edits reverted between snapshots.
    """
    result = {}
    for role, path in paths.items():
        record = {"path": str(Path(path).absolute())}
        try:
            source_path = Path(path).resolve(strict=True)
            record["path"] = str(source_path)
            if not stat.S_ISREG(source_path.stat().st_mode):
                raise ValueError("Input is not a regular file")
            digest = hashlib.sha256()
            # O_NONBLOCK also prevents a file replaced by a FIFO after stat from
            # wedging the gate. It has no effect on ordinary regular-file reads.
            with os.fdopen(os.open(source_path, os.O_RDONLY | os.O_NONBLOCK), "rb") as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("Input is not a regular file")
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                after = os.fstat(source.fileno())
            current = source_path.stat()
            signature = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                       value.st_mtime_ns, value.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current):
                raise ValueError("Input changed while hashing")
            record.update(size=after.st_size, sha256=digest.hexdigest())
        except (OSError, ValueError) as error:
            record["error"] = f"{type(error).__name__}: {error}"
        result[role] = record
    return result


def _identity_valid(record):
    return (isinstance(record, dict) and not record.get("error") and
            isinstance(record.get("path"), str) and Path(record["path"]).is_absolute() and
            type(record.get("size")) is int and record["size"] >= 0 and
            isinstance(record.get("sha256"), str) and
            re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is not None)


def _input_gaps(before, after, required_roles):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return ["Missing input snapshots"]
    if any(not isinstance(role, str) or not role for role in (*before, *after, *required_roles)):
        return ["Input roles must be nonempty strings"]
    gaps = []
    roles = set(before) | set(after) | set(required_roles)
    if not roles:
        return ["No input identities recorded"]
    for role in sorted(roles):
        left, right = before.get(role), after.get(role)
        if not _identity_valid(left) or not _identity_valid(right):
            gaps.append(f"Missing or unreadable input identity: {role}")
        elif any(left[key] != right[key] for key in ("path", "size", "sha256")):
            gaps.append(f"Input changed during runtime: {role}")
    return gaps


def verify_inputs(before, after):
    gaps = _input_gaps(before, after, ())
    return {"schema_version": 1, "status": "incomplete" if gaps else "passed",
            "gaps": gaps, "before": before, "after": after}


def evidence_status(proof, required_roles=REQUIRED_INPUTS):
    """Validate recorded evidence without requiring historical input paths to still exist."""
    if (not isinstance(proof, dict) or type(proof.get("schema_version")) is not int or
            proof["schema_version"] != 1 or proof.get("status") != "passed" or
            proof.get("gaps") != []):
        return "incomplete"
    return "incomplete" if _input_gaps(proof.get("before"), proof.get("after"), required_roles) else "passed"


def begin_worker(config_path):
    """Call before DeSmuME construction in the fresh child process."""
    if config_path is None:
        return {"config_path": None, "config_empty_before_native": False,
                "xdg_config_home": os.environ.get("XDG_CONFIG_HOME"), "pid": os.getpid()}
    config = Path(config_path).resolve()
    try:
        empty = config.is_dir() and next(config.iterdir(), None) is None
    except OSError:
        empty = False
    environment_path = os.environ.get("XDG_CONFIG_HOME")
    return {"config_path": str(config), "config_empty_before_native": empty,
            "xdg_config_home": str(Path(environment_path).resolve()) if environment_path else None,
            "xdg_config_home_raw": environment_path, "pid": os.getpid()}


def worker_environment(emu, isolation):
    """Record loaded library identity without calling undocumented native symbols."""
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    name = getattr(getattr(emu, "lib", None), "_name", None)
    native = capture_inputs({"native": name})["native"] if isinstance(name, str) and Path(name).is_absolute() else {
        "error": "Loaded library path is unavailable or unresolved", "loader_name": str(name)}
    return {"schema_version": 1, "isolation": dict(isolation), "native_library": native,
            "native_version": {"value": None, "reason": "py-desmume exposes no version query"},
            "packages": versions, "python": sys.version, "platform": platform.platform(),
            "settings": dict(KNOWN_SETTINGS), "clock": dict(CLOCK)}


def worker_environment_status(record):
    if not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1:
        return "incomplete"
    isolation = record.get("isolation")
    if not isinstance(isolation, dict):
        return "incomplete"
    path = isolation.get("config_path")
    versions = record.get("packages")
    if (not isinstance(path, str) or not Path(path).is_absolute() or
            isolation.get("xdg_config_home") != path or
            isolation.get("config_empty_before_native") is not True or
            type(isolation.get("pid")) is not int or isolation["pid"] <= 0 or
            not _identity_valid(record.get("native_library")) or
            not isinstance(versions, dict) or any(not isinstance(versions.get(p), str) or
                                                 not versions[p].strip() for p in PACKAGES) or
            any(not isinstance(record.get(key), str) or not record[key] for key in ("python", "platform")) or
            record.get("settings") != KNOWN_SETTINGS or record.get("clock") != CLOCK or
            record.get("native_version") != {"value": None, "reason": "py-desmume exposes no version query"}):
        return "incomplete"
    # bool/int equality must not let malformed JSON claim the actual settings.
    if any(type(record["settings"].get(key)) is not type(value) for key, value in KNOWN_SETTINGS.items()):
        return "incomplete"
    if record["clock"].get("controlled") is not False:
        return "incomplete"
    return "passed"


def pair_environment_status(zh, en):
    if worker_environment_status(zh) != "passed" or worker_environment_status(en) != "passed":
        return "incomplete"
    if any(zh["isolation"][key] == en["isolation"][key] for key in ("config_path", "pid")):
        return "incomplete"
    if any(zh[key] != en[key] for key in ("packages", "python", "platform", "settings", "clock", "native_version")):
        return "incomplete"
    if any(zh["native_library"][key] != en["native_library"][key] for key in ("sha256", "size")):
        return "incomplete"
    return "passed"
