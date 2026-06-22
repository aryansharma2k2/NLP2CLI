import os
import pwd
import shlex
import subprocess
from datetime import datetime


def execute_command(command, working_directory):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            cwd=working_directory,
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as exc:
        return f"Error executing command: {str(exc)}"


def get_file_context(directory):
    context = []
    try:
        for fname in os.listdir(directory):
            path = os.path.join(directory, fname)
            stat = os.stat(path)
            context.append({
                "name": fname,
                "owner": pwd.getpwuid(stat.st_uid).pw_name,
                "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d"),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                "size": stat.st_size,
                "type": "directory" if os.path.isdir(path) else "file",
            })
    except Exception as exc:
        print(f"Error accessing directory: {str(exc)}")
    return context


def validate_and_correct_command(command):
    print(command)
    args = shlex.split(command)
    corrected_args = []

    for arg in args:
        if arg.startswith("find."):
            corrected_args.append(arg.replace("find.", "find ."))
        else:
            corrected_args.append(arg)

    corrected_command = " ".join(corrected_args)
    print(corrected_command)
    return corrected_command
