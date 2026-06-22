import os
import re
import shlex
from dataclasses import dataclass

try:
    import anthropic
except ImportError:
    anthropic = None


CLAUDE_MODEL_ID = os.environ.get("NL2CLI_MODEL_ID", "claude-haiku-4-5-20251001")
DEFAULT_GENERATOR = os.environ.get("NL2CLI_GENERATOR", "auto").lower()
SUPPORTED_GENERATORS = {"auto", "claude", "fallback"}


@dataclass
class GenerationResult:
    command: str
    provider: str
    model_id: str = ""
    error: str = ""


def generate_command(input_text, context=None, history=None):
    generator = DEFAULT_GENERATOR if DEFAULT_GENERATOR in SUPPORTED_GENERATORS else "auto"

    if generator == "fallback":
        return generate_with_fallback(input_text)

    result = generate_with_claude(input_text)
    if result.command:
        return result

    return generate_with_fallback(input_text, result.error)


def generate_with_fallback(input_text, error=""):
    return GenerationResult(
        command=fallback_bash_command(input_text),
        provider="fallback",
        error=error,
    )


def generate_with_claude(input_text):
    if anthropic is None:
        return GenerationResult(
            command="",
            provider="claude",
            error="Install the 'anthropic' package to enable Claude generation.",
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return GenerationResult(
            command="",
            provider="claude",
            error="ANTHROPIC_API_KEY is not set.",
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=CLAUDE_MODEL_ID,
            max_tokens=100,
            system=(
                "You are a bash command generator. "
                "Given a natural language instruction, respond with ONLY the bash command. "
                "No explanation, no markdown, no code fences. Just the raw command."
            ),
            messages=[{"role": "user", "content": input_text}],
        )
        command = message.content[0].text.strip().strip("`")
        for prefix in ("bash\n", "sh\n"):
            if command.startswith(prefix):
                command = command[len(prefix):].strip()
        return GenerationResult(
            command=command,
            provider="claude",
            model_id=message.model,
        )
    except Exception as exc:
        return GenerationResult(
            command="",
            provider="claude",
            error=str(exc),
        )


def fallback_bash_command(input_text):
    text = input_text.lower().strip()
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", input_text)

    if ("current directory" in text or "where am i" in text) and "list" not in text:
        return "pwd"

    if "list" in text and any(w in text for w in ("file", "folder", "directory", "content")):
        return "ls -la"
    if "hidden" in text and any(w in text for w in ("file", "folder")):
        return "ls -la"

    if any(w in text for w in ("find", "search")) and "name" in text and "file" in text:
        if quoted:
            return f"find . -name '*{quoted[0]}*'"
        return "find . -type f"

    if any(w in text for w in ("find", "search", "show")) and "file" in text:
        if "python" in text or ".py" in text:
            return "find . -name '*.py' -type f"
        if "large" in text:
            return "find . -type f -size +10M"
        if quoted:
            return f"find . -name '*{quoted[0]}*'"
        return "find . -type f"

    if "disk" in text and any(w in text for w in ("usage", "space")):
        return "du -sh ."

    if "git status" in text or ("status" in text and "git" in text):
        return "git status --short"

    if any(w in text for w in ("create", "make", "new")) and any(w in text for w in ("directory", "folder")):
        name = quoted[0] if quoted else "new_folder"
        return f"mkdir {shlex.quote(name)}"

    if "copy" in text and "file" in text and len(quoted) >= 2:
        if len(quoted) >= 3:
            src_file, src_dir, dst = quoted[0], quoted[1], quoted[2]
            return f"cp {shlex.quote(src_dir + '/' + src_file)} {shlex.quote(dst)}"
        return f"cp {shlex.quote(quoted[0])} {shlex.quote(quoted[1])}"
    if "copy" in text and len(quoted) >= 2:
        return f"cp {shlex.quote(quoted[0])} {shlex.quote(quoted[-1])}"

    if any(w in text for w in ("delete", "remove")) and any(w in text for w in ("all", "files", "everything")):
        if quoted:
            return f"rm -rf {shlex.quote(quoted[0])}/*"
        return "rm -rf ./*"

    if any(w in text for w in ("delete", "remove")):
        if quoted:
            return f"rm -i {shlex.quote(quoted[0])}"
        return "rm -i target_file"

    return "echo 'No confident command generated. Try a more specific instruction.'"
