import os
import shlex
from dataclasses import dataclass


HIGH_RISK_COMMANDS = {
    "rm",
    "rmdir",
    "dd",
    "mkfs",
    "fdisk",
    "diskutil",
    "shutdown",
    "reboot",
    "halt",
    "sudo",
    "su",
    "chmod",
    "chown",
    "curl",
    "wget",
}

MEDIUM_RISK_COMMANDS = {
    "mv",
    "cp",
    "touch",
    "mkdir",
    "python",
    "python3",
    "pip",
    "pip3",
    "npm",
    "npx",
    "git",
}

HIGH_RISK_PATTERNS = {
    "rm -rf": "recursive forced deletion",
    "rm -fr": "recursive forced deletion",
    ">": "file overwrite or redirect",
    ">>": "file append redirect",
    "| sh": "remote or piped shell execution",
    "| bash": "remote or piped shell execution",
    "$(": "command substitution",
    "`": "command substitution",
}

COMMAND_EXPLANATIONS = {
    "ls": "Lists files and folders.",
    "pwd": "Prints the current working directory.",
    "cd": "Changes the current working directory.",
    "find": "Searches for files or folders that match filters.",
    "grep": "Searches text for matching lines.",
    "cat": "Prints file contents.",
    "head": "Shows the start of a file.",
    "tail": "Shows the end of a file.",
    "mkdir": "Creates a new directory.",
    "touch": "Creates a file or updates its timestamp.",
    "cp": "Copies files or folders.",
    "mv": "Moves or renames files or folders.",
    "rm": "Deletes files or folders.",
    "chmod": "Changes file permissions.",
    "chown": "Changes file ownership.",
    "git": "Runs a Git operation.",
}


@dataclass
class CommandAnalysis:
    risk: str
    summary: str
    findings: list
    requires_confirmation: bool
    safer_alternative: str = ""


def analyze_command(command):
    normalized_command = " ".join(command.strip().split())
    findings = []
    risk_score = 0

    if not normalized_command:
        return CommandAnalysis(
            risk="unknown",
            summary="No command was provided.",
            findings=["Enter a command before execution."],
            requires_confirmation=True,
        )

    try:
        args = shlex.split(normalized_command)
    except ValueError as exc:
        return CommandAnalysis(
            risk="high",
            summary="The command could not be parsed safely.",
            findings=[f"Shell parsing error: {exc}"],
            requires_confirmation=True,
        )

    executable = os.path.basename(args[0]) if args else ""
    if executable in HIGH_RISK_COMMANDS:
        risk_score += 3
        findings.append(f"`{executable}` can modify the system, delete data, or run external code.")
    elif executable in MEDIUM_RISK_COMMANDS:
        risk_score += 1
        findings.append(f"`{executable}` may change files or project state.")

    lowered = normalized_command.lower()
    for pattern, reason in HIGH_RISK_PATTERNS.items():
        if pattern in lowered:
            risk_score += 2
            findings.append(f"Detected {reason}: `{pattern}`.")

    if any(operator in normalized_command for operator in [";", "&&", "||"]):
        risk_score += 1
        findings.append("The command chains multiple shell operations.")

    if executable == "find" and "-delete" in args:
        risk_score += 3
        findings.append("`find -delete` can remove many files at once.")

    if executable == "rm" and ("-i" not in args and "--interactive" not in args):
        findings.append("Consider adding `-i` to confirm each deletion interactively.")

    if not findings:
        findings.append("No obvious risky patterns detected.")

    if risk_score >= 3:
        risk = "high"
    elif risk_score >= 1:
        risk = "medium"
    else:
        risk = "low"

    summary = COMMAND_EXPLANATIONS.get(executable, "Runs a shell command.")
    safer_alternative = suggest_safer_alternative(args, normalized_command)

    return CommandAnalysis(
        risk=risk,
        summary=summary,
        findings=findings,
        requires_confirmation=risk == "high",
        safer_alternative=safer_alternative,
    )


def suggest_safer_alternative(args, command):
    if not args:
        return ""

    executable = os.path.basename(args[0])
    if executable == "rm" and "-i" not in args and "--interactive" not in args:
        return command.replace("rm", "rm -i", 1)
    if executable == "find" and "-delete" in args:
        preview_args = [arg for arg in args if arg != "-delete"]
        return " ".join(shlex.quote(arg) for arg in preview_args)
    if ">" in command and ">>" not in command:
        return "Review the target file first, or use `>>` if you meant to append instead of overwrite."
    return ""
