import os
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
