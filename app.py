import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from commands import execute_command, get_file_context, validate_and_correct_command
from generators import DEFAULT_GENERATOR, generate_command
from preview import preview_command
from safety import analyze_command


SESSION_FILE = Path("session.json")

app = Flask(__name__)


def load_history():
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            return []
    return []


def save_history(history):
    try:
        SESSION_FILE.write_text(json.dumps(history, indent=2))
    except Exception as exc:
        print(f"Failed to save session: {exc}")


def build_markdown_export(history):
    lines = [
        "# NL2CLI Session Export",
        "",
        f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
    ]

    if not history:
        lines.append("*No commands have been executed in this session.*")
        return "\n".join(lines)

    for i, entry in enumerate(history, 1):
        instruction = entry.get("instruction", "")
        command = entry.get("command", "")
        output = entry.get("output", "").strip()
        risk = entry.get("analysis", {}).get("risk", "unknown")
        executed_at = entry.get("executed_at", "")

        heading = instruction or command
        lines += [
            "---",
            "",
            f"## {i}. {heading}",
            "",
        ]
        if instruction:
            lines += [f"**Intent:** {instruction}", ""]
        lines += [
            f"**Command:** `{command}`  ",
            f"**Risk:** {risk}  ",
            f"**Executed:** {executed_at}",
            "",
            "**Output:**",
            "```",
            output or "(no output)",
            "```",
            "",
        ]

    return "\n".join(lines)


history = load_history()


@app.route("/")
def index():
    directories = [os.path.abspath(d) for d in os.listdir(".") if os.path.isdir(d)]
    return render_template(
        "index.html",
        directories=directories,
        history=history,
        current_year=datetime.now().year,
    )


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    user_input = data.get("instruction", "")
    directory = data.get("directory", ".")
    if not user_input:
        return jsonify({"error": "No input provided"}), 400

    try:
        file_context = get_file_context(directory)
        generation = generate_command(user_input, file_context, history)
        generated_command = validate_and_correct_command(generation.command)
        analysis = analyze_command(generated_command)
        return jsonify({
            "generated_command": generated_command,
            "analysis": asdict(analysis),
            "model_status": {
                "provider": generation.provider,
                "model_id": generation.model_id or None,
                "error": generation.error or None,
                "mode": DEFAULT_GENERATOR,
            },
        })
    except Exception as exc:
        print(str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route("/execute", methods=["POST"])
def execute():
    data = request.json
    command = data.get("command", "")
    directory = data.get("directory", ".")
    instruction = data.get("instruction", "")
    confirmed_high_risk = data.get("confirmed_high_risk", False)
    if not command:
        return jsonify({"error": "No command provided"}), 400

    try:
        analysis = analyze_command(command)
        if analysis.requires_confirmation and not confirmed_high_risk:
            return jsonify({
                "error": "High-risk command requires explicit confirmation.",
                "analysis": asdict(analysis),
            }), 403

        output = execute_command(command, directory)
        entry = {
            "instruction": instruction,
            "command": command,
            "output": output,
            "analysis": asdict(analysis),
            "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        history.append(entry)
        save_history(history)
        return jsonify({"output": output, "analysis": asdict(analysis)})
    except Exception as exc:
        print(str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route("/preview", methods=["POST"])
def preview():
    data = request.json
    command = data.get("command", "")
    directory = data.get("directory", ".")
    if not command:
        return jsonify({"error": "No command provided"}), 400
    try:
        result = preview_command(command, directory)
        return jsonify(asdict(result))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/clear", methods=["POST"])
def clear():
    history.clear()
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    return jsonify({"ok": True})


@app.route("/export")
def export():
    md = build_markdown_export(history)
    return Response(
        md,
        mimetype="text/markdown",
        headers={"Content-Disposition": "attachment; filename=nl2cli-session.md"},
    )


if __name__ == "__main__":
    app.run(debug=True)
