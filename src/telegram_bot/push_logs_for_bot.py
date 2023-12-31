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
from telegram_bot.utilities import push_log

# SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))


def push_general_logs():
    general_log_file = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_log"
    name_to_file = {"general_logs": general_log_file}
    push_log(name_to_file)


def push_health_logs():
    security_log_file = os.getenv('SECURITY_LOGFILE') if os.getenv('SECURITY_LOGFILE') else "telegram_bot_security_file"
    name_to_file = {"health_logs": security_log_file}
    push_log(name_to_file)


def push_logs():
    push_general_logs()
    push_health_logs()


#
# def push_logs():
#     # todo -- review the default variables as they are different across different files
#     security_log_file = os.getenv('SECURITY_LOGFILE') if os.getenv('SECURITY_LOGFILE') else "telegram_bot_security_file"
#     general_log_file = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_log"
#     rsa_id_path = os.getenv('RSA_ID_PATH')
#     remote_directory_path = os.getenv('REMOTE_PATH')  # user@host:path_to_directory
#
#     if not rsa_id_path or not remote_directory_path:
#         print(f'skipping push to remote. Set RSA_ID_PATH and REMOTE_PATH to send to remote.')
#         return
#
#     # Check if all necessary environment variables are set
#     required_vars = ['SECURITY_LOGFILE', 'GENERAL_LOGFILE', 'RSA_ID_PATH', 'REMOTE_PATH']
#     missing_vars = [var for var in required_vars if os.getenv(var) is None]
#
#     # if missing_vars:
#     #     missing_vars_str = ', '.join(missing_vars)
#     #     log_to_bot(f"Error: The following environment variables are not set: {missing_vars_str}")
#     #     raise Exception(f"Missing environment variables: {missing_vars_str}")
#
#     if not os.path.isfile(rsa_id_path):
#         # print(f"{rsa_id_path}, the rsa id path, does not exist")
#         raise Exception(f"{rsa_id_path}, the rsa id path, does not exist")
#
#     name_to_file = {
#         "health_logs": security_log_file,
#         "general_logs": general_log_file
#     }
#
#     for saving_convention, log_file_path in name_to_file.items():
#         file_name = f'{saving_convention}.{hostname}.json'
#         temp_remote_path = os.path.join(remote_directory_path, file_name)
#         cmd = f'scp -i {rsa_id_path} {log_file_path} {temp_remote_path}'
#
#         # Alternative with rsync (uncomment to use):
#         cmd = f'rsync -avz -e "ssh -i {rsa_id_path} -o StrictHostKeyChecking=no" {log_file_path} {temp_remote_path}'
#         # run(cmd)
#         run(cmd)
#
#         delete_entries_older_than_x_days(log_file_path)


if __name__ == "__main__":
    push_logs()
