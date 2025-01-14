import subprocess
from flask import Flask, render_template, request, jsonify
import torch
from transformers import RobertaTokenizer, T5ForConditionalGeneration
import os
from datetime import datetime
import pwd
import shlex

app = Flask(__name__)

if torch.backends.mps.is_available():
    device = torch.device("mps")
    print("MPS backend is available.")
elif torch.cuda.is_available():
    device = torch.device("cuda")
    print("CUDA backend is available.")
else:
    device = torch.device("cpu")
    print("Using CPU.")

# Load the model and tokenizer
model = T5ForConditionalGeneration.from_pretrained("./model").to(device)
tokenizer = RobertaTokenizer.from_pretrained("./model")

model.eval()

history = []  # To store the history of commands executed

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

def generate_bash_command(model, tokenizer, input_text, device, context=None):
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

    inputs = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=512).to(device)

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

        outputs = model.generate(
            inputs["input_ids"],
            max_new_tokens=50,
            length_penalty=0.8,
            no_repeat_ngram_size=2,
            repetition_penalty=1.2,
            num_return_sequences=1,
            num_beams=5,
            early_stopping=True,
            eos_token_id=tokenizer.eos_token_id,
        )

    predicted_cmd = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return predicted_cmd.strip()


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
    return render_template('index.html', directories=directories, history=history)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    user_input = data.get('instruction', '')
    directory = data.get('directory', '.')
    if not user_input:
        return jsonify({"error": "No input provided"}), 400

    try:
        file_context = get_file_context(directory)
        generated_command = generate_bash_command(model, tokenizer, user_input, device, file_context)
        generated_command = validate_and_correct_command(generated_command)
        return jsonify({"generated_command": generated_command})
    except Exception as e:
        print(str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/execute', methods=['POST'])
def execute():
    data = request.json
    command = data.get('command', '')
    directory = data.get('directory', '.')
    if not command:
        return jsonify({"error": "No command provided"}), 400

    try:
        output = execute_command(command, directory)
        history.append({"command": command, "output": output})
        return jsonify({"output": output})
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