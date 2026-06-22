import os
import shlex
import subprocess
from dataclasses import dataclass

READ_ONLY_EXECUTABLES = frozenset({
    "ls", "find", "cat", "head", "tail", "grep",
    "pwd", "du", "df", "wc", "echo", "which",
    "file", "stat", "date", "whoami", "hostname", "uname",
})


@dataclass
class PreviewResult:
    available: bool
    mode: str    # "live" | "impact" | "none"
    label: str
    output: str = ""


def preview_command(command: str, directory: str) -> PreviewResult:
    try:
        args = shlex.split(command.strip())
    except ValueError:
        return PreviewResult(available=False, mode="none", label="")

    if not args:
        return PreviewResult(available=False, mode="none", label="")

    executable = os.path.basename(args[0])

    if executable in READ_ONLY_EXECUTABLES:
        return _live_preview(command, directory)

    return _impact_preview(executable, args, directory)


def _live_preview(command: str, directory: str) -> PreviewResult:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=directory,
        )
        output = result.stdout or result.stderr or "(no output)"
        return PreviewResult(
            available=True,
            mode="live",
            label="Live preview — read-only, safe to run",
            output=output.strip(),
        )
    except subprocess.TimeoutExpired:
        return PreviewResult(available=False, mode="none", label="Preview timed out.")
    except Exception as exc:
        return PreviewResult(available=False, mode="none", label=f"Preview error: {exc}")


def _impact_preview(executable: str, args: list, directory: str) -> PreviewResult:
    if executable == "rm":
        return _rm_impact(args, directory)
    if executable in ("cp", "mv"):
        return _copy_move_impact(executable, args)
    if executable == "mkdir":
        return _mkdir_impact(args)
    if executable == "touch":
        return _touch_impact(args)
    return PreviewResult(available=False, mode="none", label="")


def _has_recursive_flag(args: list) -> bool:
    for arg in args:
        if arg in ("-r", "-R", "--recursive"):
            return True
        if arg.startswith("-") and not arg.startswith("--") and ("r" in arg or "R" in arg):
            return True
    return False


def _rm_impact(args: list, directory: str) -> PreviewResult:
    targets = [a for a in args[1:] if not a.startswith("-")]
    if not targets:
        return PreviewResult(
            available=True,
            mode="impact",
            label="Files that would be deleted",
            output="No target path specified.",
        )

    recursive = _has_recursive_flag(args)
    lines = []
    for target in targets:
        # Strip trailing /* so we can stat the directory directly
        if target.endswith("/*"):
            target = target[:-2]
            recursive = True
        path = target if os.path.isabs(target) else os.path.join(directory, target)
        if os.path.isdir(path) and recursive:
            try:
                result = subprocess.run(
                    ["find", path, "-maxdepth", "3"],
                    capture_output=True, text=True, timeout=3,
                )
                found = result.stdout.strip().splitlines()
                lines.extend(found[:30])
                if len(found) > 30:
                    lines.append(f"... and {len(found) - 30} more")
            except Exception:
                lines.append(f"{path}/ (could not list contents)")
        elif os.path.exists(path):
            lines.append(path)
        else:
            lines.append(f"{path} (not found)")

    return PreviewResult(
        available=True,
        mode="impact",
        label="Files that would be deleted",
        output="\n".join(lines) or "No matching files.",
    )


def _copy_move_impact(executable: str, args: list) -> PreviewResult:
    targets = [a for a in args[1:] if not a.startswith("-")]
    if len(targets) < 2:
        return PreviewResult(
            available=True,
            mode="impact",
            label="What this command will do",
            output="Missing source or destination.",
        )
    src, dst = targets[0], targets[-1]
    verb = "Copy" if executable == "cp" else "Move / rename"
    return PreviewResult(
        available=True,
        mode="impact",
        label="What this command will do",
        output=f"{verb}:  {src}  →  {dst}",
    )


def _mkdir_impact(args: list) -> PreviewResult:
    targets = [a for a in args[1:] if not a.startswith("-")]
    noun = "directories" if len(targets) > 1 else "directory"
    names = ",  ".join(targets) if targets else "(unspecified)"
    return PreviewResult(
        available=True,
        mode="impact",
        label="What this command will do",
        output=f"Create {noun}:  {names}",
    )


def _touch_impact(args: list) -> PreviewResult:
    targets = [a for a in args[1:] if not a.startswith("-")]
    names = ",  ".join(targets) if targets else "(unspecified)"
    return PreviewResult(
        available=True,
        mode="impact",
        label="What this command will do",
        output=f"Create or update timestamp:  {names}",
    )
