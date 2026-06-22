import os
import re
import shlex
from dataclasses import dataclass

try:
    import torch
    from transformers import RobertaTokenizer, T5ForConditionalGeneration
except ImportError:
    torch = None
    RobertaTokenizer = None
    T5ForConditionalGeneration = None


DEFAULT_MODEL_ID = os.environ.get(
    "NL2CLI_MODEL_ID",
    os.environ.get("NLP2CLI_MODEL_ID", "JayProngs/NL2BASH"),
)
DEFAULT_GENERATOR = os.environ.get("NL2CLI_GENERATOR", "auto").lower()
SUPPORTED_GENERATORS = {"auto", "huggingface", "fallback"}

model = None
tokenizer = None
device = None
model_load_error = None


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

    result = generate_with_huggingface(input_text, context, history)
    if result.command:
        return result

    return generate_with_fallback(input_text, result.error)


def generate_with_fallback(input_text, error=""):
    return GenerationResult(
        command=fallback_bash_command(input_text),
        provider="fallback",
        error=error,
    )


def generate_with_huggingface(input_text, context=None, history=None):
    loaded_model, loaded_tokenizer, loaded_device = load_model()

    if loaded_model is None or loaded_tokenizer is None:
        return GenerationResult(
            command="",
            provider="huggingface",
            model_id=DEFAULT_MODEL_ID,
            error=model_load_error or "Hugging Face model is unavailable.",
        )

    prompt = build_prompt(input_text, context, history)
    print(prompt)

    inputs = loaded_tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(loaded_device)

    with torch.no_grad():
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


def build_prompt(input_text, context=None, history=None):
    # Context and history are explicit parameters now, but disabled until we add previews/evals.
    if context and False:
        formatted_context = "Current directory contents:\n"
        for file_info in context:
            formatted_context += (
                f"{file_info['name']} ({file_info['type']}) - "
                f"Owner: {file_info['owner']}, Created: {file_info['created']}\n"
            )
        input_text = f"Context: {formatted_context}\nQuery: {input_text}"

    if history and False:
        formatted_history = "Previous interactions:\n"
        for entry in history[-5:]:
            instruction = entry.get("instruction", "N/A")
            formatted_history += f"User: {instruction}\n"
            formatted_history += f"Command: {entry['command']}\n"
            formatted_history += f"Output: {entry['output']}\n"
        input_text = f"{formatted_history}\nCurrent instruction: {input_text}"

    return f"bash: {input_text}"


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


def fallback_bash_command(input_text):
    text = input_text.lower().strip()
    # Quoted names in the original instruction, e.g. 'test_folder' or "config.json"
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", input_text)

    if "current directory" in text or "where am i" in text:
        return "pwd"

    if "list" in text and any(w in text for w in ("file", "folder", "directory", "content")):
        return "ls -la"
    if "hidden" in text and any(w in text for w in ("file", "folder")):
        return "ls -la"

    # find by name / keyword in filename
    if any(w in text for w in ("find", "search")) and "name" in text and "file" in text:
        if quoted:
            return f"find . -name '*{quoted[0]}*'"
        return "find . -type f"

    # find by type / extension
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

    # mkdir
    if any(w in text for w in ("create", "make", "new")) and any(w in text for w in ("directory", "folder")):
        name = quoted[0] if quoted else "new_folder"
        return f"mkdir {shlex.quote(name)}"

    # cp — "Copy file 'x' from 'src_dir' to 'dst_dir'"
    if "copy" in text and "file" in text and len(quoted) >= 2:
        if len(quoted) >= 3:
            src_file, src_dir, dst = quoted[0], quoted[1], quoted[2]
            return f"cp {shlex.quote(src_dir + '/' + src_file)} {shlex.quote(dst)}"
        return f"cp {shlex.quote(quoted[0])} {shlex.quote(quoted[1])}"
    if "copy" in text and len(quoted) >= 2:
        return f"cp {shlex.quote(quoted[0])} {shlex.quote(quoted[-1])}"

    # rm — "delete all files in 'dir'"
    if any(w in text for w in ("delete", "remove")) and any(w in text for w in ("all", "files", "everything")):
        if quoted:
            return f"rm -rf {shlex.quote(quoted[0])}/*"
        return "rm -rf ./*"

    # rm — specific file
    if any(w in text for w in ("delete", "remove")):
        if quoted:
            return f"rm -i {shlex.quote(quoted[0])}"
        return "rm -i target_file"

    return "echo 'No confident command generated. Try a more specific instruction.'"
