import subprocess
from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
import pwd
import shlex
from dataclasses import dataclass, asdict

try:
    import torch
    from transformers import RobertaTokenizer, T5ForConditionalGeneration
except ImportError:
    torch = None
    RobertaTokenizer = None
    T5ForConditionalGeneration = None

app = Flask(__name__)

DEFAULT_MODEL_ID = os.environ.get(
    "NL2CLI_MODEL_ID",
    os.environ.get("NLP2CLI_MODEL_ID", "JayProngs/NL2BASH"),
)
DEFAULT_GENERATOR = os.environ.get("NL2CLI_GENERATOR", "auto").lower()
model = None
tokenizer = None
device = None
model_load_error = None

history = []  # To store the history of commands executed

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


@dataclass
class GenerationResult:
    command: str
    provider: str
    model_id: str = ""
    error: str = ""


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

def execute_command(command, working_directory):
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=5, cwd=working_directory
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def get_inference_device():
    if torch is None:
        return None
    if torch.backends.mps.is_available():
        print("MPS backend is available.")
        return torch.device("mps")
    if torch.cuda.is_available():
        print("CUDA backend is available.")
        return torch.device("cuda")
    print("Using CPU.")
    return torch.device("cpu")


def load_model():
    global model, tokenizer, device, model_load_error

    if model is not None and tokenizer is not None:
        return model, tokenizer, device

    if torch is None or RobertaTokenizer is None or T5ForConditionalGeneration is None:
        model_load_error = "Install torch and transformers to enable model inference."
        return None, None, None

    try:
        device = get_inference_device()
        model = T5ForConditionalGeneration.from_pretrained(DEFAULT_MODEL_ID).to(device)
        tokenizer = RobertaTokenizer.from_pretrained(DEFAULT_MODEL_ID)
        model.eval()
        model_load_error = None
        return model, tokenizer, device
    except Exception as exc:
        model_load_error = str(exc)
        print(f"Model unavailable, using fallback rules: {model_load_error}")
        return None, None, None


def fallback_bash_command(input_text):
    text = input_text.lower().strip()

    if "current directory" in text or "where am i" in text:
        return "pwd"
    if "list" in text and ("file" in text or "folder" in text or "directory" in text):
        return "ls -la"
    if "hidden" in text and ("file" in text or "folder" in text):
        return "ls -la"
    if "python" in text and "file" in text and ("find" in text or "show" in text):
        return "find . -name '*.py' -type f"
    if "large" in text and "file" in text:
        return "find . -type f -size +10M"
    if "disk" in text and ("usage" in text or "space" in text):
        return "du -sh ."
    if "git status" in text or ("status" in text and "git" in text):
        return "git status --short"
    if "make" in text and "directory" in text:
        return "mkdir new_folder"
    if "delete" in text or "remove" in text:
        return "rm -i target_file"

    return "echo 'No confident command generated. Try a more specific instruction.'"


def generate_command(input_text, context=None):
    generator = DEFAULT_GENERATOR if DEFAULT_GENERATOR in {"auto", "huggingface", "fallback"} else "auto"

    if generator == "fallback":
        return generate_with_fallback(input_text)

    result = generate_with_huggingface(input_text, context)
    if result.command:
        return result

    return generate_with_fallback(input_text, result.error)


def generate_with_fallback(input_text, error=""):
    return GenerationResult(
        command=fallback_bash_command(input_text),
        provider="fallback",
        error=error,
    )


def generate_with_huggingface(input_text, context=None):
    loaded_model, loaded_tokenizer, loaded_device = load_model()

    if loaded_model is None or loaded_tokenizer is None:
        return GenerationResult(
            command="",
            provider="huggingface",
            model_id=DEFAULT_MODEL_ID,
            error=model_load_error or "Hugging Face model is unavailable.",
        )

    # Format context as structured text
    if context and 1!=1:
        formatted_context = "Current directory contents:\n"
        for file_info in context:
            formatted_context += f"{file_info['name']} ({file_info['type']}) - Owner: {file_info['owner']}, Created: {file_info['created']}\n"
        input_text = f"Context: {formatted_context}\nQuery: {input_text}"

    if history and 1!=1:
        formatted_history = "Previous interactions:\n"
        for entry in history[-5:]:  # Include last 5 interactions
            # Ensure that 'instruction' exists in the entry
            instruction = entry.get('instruction', 'N/A')
            formatted_history += f"User: {instruction}\n"
            formatted_history += f"Command: {entry['command']}\n"
            formatted_history += f"Output: {entry['output']}\n"
        input_text = f"{formatted_history}\nCurrent instruction: {input_text}"

    # Adding prompt engineering to ensure bash output
    input_text = f"bash: {input_text}"
    print(input_text)

    inputs = loaded_tokenizer(input_text, return_tensors="pt", truncation=True, max_length=512).to(loaded_device)

    with torch.no_grad():
        # check which gives better response
        # outputs = model.generate(
        #     inputs["input_ids"],
        #     max_new_tokens=50,
        #     num_return_sequences=3,
        #     temperature=0.3,
        #     top_p=0.9,
        #     top_k=50,
        #     do_sample=True,
        #     eos_token_id=tokenizer.eos_token_id,
        # )

        outputs = loaded_model.generate(
            inputs["input_ids"],
            max_new_tokens=50,
            length_penalty=0.8,
            no_repeat_ngram_size=2,
            repetition_penalty=1.2,
            num_return_sequences=1,
            num_beams=5,
            early_stopping=True,
            eos_token_id=loaded_tokenizer.eos_token_id,
        )

    predicted_cmd = loaded_tokenizer.decode(outputs[0], skip_special_tokens=True)
    return GenerationResult(
        command=predicted_cmd.strip(),
        provider="huggingface",
        model_id=DEFAULT_MODEL_ID,
    )


def get_file_context(directory):
    context = []
    try:
        for fname in os.listdir(directory):
            stat = os.stat(os.path.join(directory, fname))
            file_info = {
                'name': fname,
                'owner': pwd.getpwuid(stat.st_uid).pw_name,
                'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d'),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d'),
                'size': stat.st_size,
                'type': 'directory' if os.path.isdir(os.path.join(directory, fname)) else 'file'
            }
            context.append(file_info)
    except Exception as e:
        print(f"Error accessing directory: {str(e)}")
    return context

def validate_and_correct_command(command):
    print(command)
    # Split the command into arguments
    args = shlex.split(command)
    # Check for 'find.' and correct it
    corrected_args = []
    for arg in args:
        if arg.startswith('find.'):
            corrected_args.append(arg.replace('find.', 'find .'))
        else:
            corrected_args.append(arg)
    # Reconstruct the command
    corrected_command = ' '.join(corrected_args)
    print(corrected_command)
    return corrected_command

@app.route('/')
def index():
    directories = [os.path.abspath(d) for d in os.listdir('.') if os.path.isdir(d)]
    return render_template(
        'index.html',
        directories=directories,
        history=history,
        current_year=datetime.now().year
    )

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('instruction', '')
    directory = data.get('directory', '.')
    if not user_input:
        return jsonify({"error": "No input provided"}), 400

    try:
        file_context = get_file_context(directory)
        generation = generate_command(user_input, file_context)
        generated_command = generation.command
        generated_command = validate_and_correct_command(generated_command)
        analysis = analyze_command(generated_command)
        return jsonify({
            "generated_command": generated_command,
            "analysis": asdict(analysis),
            "model_status": {
                "provider": generation.provider,
                "model_id": generation.model_id or None,
                "error": generation.error or None,
                "mode": DEFAULT_GENERATOR,
            }
        })
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    command = data.get('command', '')
    directory = data.get('directory', '.')
    confirmed_high_risk = data.get('confirmed_high_risk', False)
    if not command:
        return jsonify({"error": "No command provided"}), 400

    try:
        analysis = analyze_command(command)
        if analysis.requires_confirmation and not confirmed_high_risk:
            return jsonify({
                "error": "High-risk command requires explicit confirmation.",
                "analysis": asdict(analysis)
            }), 403

        output = execute_command(command, directory)
        history.append({
            "command": command,
            "output": output,
            "analysis": asdict(analysis),
            "executed_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        return jsonify({"output": output, "analysis": asdict(analysis)})
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)

# Use below user inputs to test the model:
# List all files in the current directory.
# Create a new directory called 'test_folder'.
# Copy file 'config.json' from 'model' directory to the 'test_folder' folder.
# Find all files starting with 'c' from directory 'test_folder'.
# Delete all files in the 'test_folder' directory.
# Find all files containing the word 'app' in their name.
