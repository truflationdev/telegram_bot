#!/usr/bin/env python3
"""
This script transfers log files to a remote location.
Usage:
    Ensure that the necessary environment variables are set:
    - SECURITY_LOGFILE: path to the security log file
    - GENERAL_LOGFILE: path to the general log file
    - RSA_ID_PATH: path to the RSA key for scp
    - REMOTE_PATH: remote directory path in the format user@host:path_to_directory
"""

import os
from dotenv import load_dotenv
import socket
import subprocess
from telegram_bot.utilities import delete_entries_older_than_x_days
from telegram_bot.general_logger import log_to_bot

hostname = socket.gethostname()
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
load_dotenv()

security_log_file = os.getenv('SECURITY_LOGFILE') if os.getenv('SECURITY_LOGFILE') else "telegram_bot_security_file"
general_log_file = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_security_file"
rsa_id_path = os.getenv('RSA_ID_PATH')
remote_directory_path = os.getenv('REMOTE_PATH')  # user@host:path_to_directory

# Check if all necessary environment variables are set
required_vars = ['SECURITY_LOGFILE', 'GENERAL_LOGFILE', 'RSA_ID_PATH', 'REMOTE_PATH']
missing_vars = [var for var in required_vars if os.getenv(var) is None]

if missing_vars:
    missing_vars_str = ', '.join(missing_vars)
    log_to_bot(f"Error: The following environment variables are not set: {missing_vars_str}")
    raise Exception(f"Missing environment variables: {missing_vars_str}")


def run(cmd: str) -> None:
    """
    Execute a command and log any errors.

    :param cmd: the command to execute
    """
    # print(f"CMD: {cmd}")
    try:
        ret = subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        json_error = f'"error": "while trying to run command {cmd}, an eeror occcurred: {e}"'
        log_to_bot(json_error)


def push_logs():
    name_to_file = {
        "health_logs": security_log_file,
        "general_logs": general_log_file
    }

    for saving_convention, log_file_path in name_to_file.items():
        file_name = f'{saving_convention}.{hostname}.json'
        temp_remote_path = os.path.join(remote_directory_path, file_name)
        cmd = f'scp -i {rsa_id_path} {log_file_path} {temp_remote_path}'

        # Alternative with rsync (uncomment to use):
        cmd = f'rsync -avz -e "ssh -i {rsa_id_path}" {log_file_path} {temp_remote_path}'
        # run(cmd)
        run(cmd)

        delete_entries_older_than_x_days(log_file_path)


if __name__ == "__main__":
    push_logs()
