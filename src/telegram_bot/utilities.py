import os
import json
import datetime
import time
import subprocess
from ilock import ILock
from collections import OrderedDict
from typing import Union, Dict
import socket

hostname = socket.gethostname()
log_life = int(os.getenv('LOG_LIFE') if os.getenv('LOG_LIFE') else 3)


def delete_entries_older_than_x_days(log_file_path: str, days: int = log_life) -> None:
    """
    Delete log entries older than a certain number of days.

    :param log_file_path: str: path to log file
    :param days: the number of days to keep log entries for
    """
    check_log_file(log_file_path)
    with open(log_file_path, 'r') as infile:
        json_data = infile.read()
        json_data = json_data if json_data else '{}'
        data = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(json_data)

    timestamps_to_delete = []
    current_time = time.time()  # timestamp in seconds
    for timestamp_str, data_dict in data.items():
        try:
            # If the timestamp is in seconds
            timestamp = float(timestamp_str)
        except ValueError:
            # If the timestamp is an ISO 8601 string
            timestamp = datetime.datetime.fromisoformat(timestamp_str).timestamp()

        if (current_time - days * 24 * 3600) > timestamp:
            timestamps_to_delete.append(timestamp_str)

    for timestamp_str in timestamps_to_delete:
        del data[timestamp_str]

    save_logs(data, log_file_path)


def check_log_file(log_file_path: str) -> None:
    """
    Checks if log file varaible exists. Creates file if file doesn't exist.

    :param log_file_path: str: path to log file

    """
    if not log_file_path:
        raise Exception('log_file_path is falsey.')
    if not os.path.exists(log_file_path):
        with open(log_file_path, 'w') as f:
            json.dump({}, f)


def load_logs_into_dict(log_file_path: str) -> dict:
    """
    Load the logs from the file into a dictionary.

    :return: a dictionary containing the logs
    :param log_file_path: str: path to log file
    """
    check_log_file(log_file_path)
    with open(log_file_path, 'r') as infile:
        json_data = infile.read()
        json_data = json_data if json_data else '{}'
        data = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(json_data)
    return data


def save_logs(logs_dict: dict, log_file_path: str) -> None:
    """
    Save the logs to a file.

    :param logs_dict: the logs to save
    :param log_file_path: str: path to log file
    """
    with Ilock('save_log_lock'):
        check_log_file(log_file_path)
        with open(log_file_path, "w") as outfile:
            json.dump(logs_dict, outfile, indent=4)

def process_input_data(input_data: Union[Dict, str]) -> Dict:
    """
    Processes the input data and returns a dictionary.

    :param input_data: the data to process, which can be a dictionary, a JSON string, or a non-JSON string
    """
    if isinstance(input_data, Dict):
        # If the input is a dictionary, use it directly
        return input_data
    elif isinstance(input_data, str):
        try:
            # If the input is a string, try to parse it as JSON
            return json.loads(input_data)
        except json.JSONDecodeError:
            # If parsing as JSON fails, use the string as a general message
            return {"general": input_data}
    else:
        # If the input is neither a dictionary nor a string, raise an error
        raise TypeError("input_data must be a dictionary or a string")


def log_to_bot(input_data: Union[Dict, str], log_file_path: str) -> None:
    """
    Main function to process the input data and save the logs.

    :param input_data: the data to process, which can be a dictionary, a JSON string, or a non-JSON string
    :param log_file_path: str: path to log file
    """

    data_dict = process_input_data(input_data)

    ts = datetime.datetime.utcnow().isoformat()  # ISO 8601 timestamp in UTC
    timestamped_report = {ts: data_dict}

    total_report = load_logs_into_dict(log_file_path)

    total_report.update(timestamped_report)
    save_logs(total_report, log_file_path)

    json_object = json.dumps(total_report, indent=4)
    # print(json_object)


def str_to_datetime(input_string: str) -> datetime:
    try:
        # First, try to interpret the input as a timestamp
        timestamp = float(input_string)
        return datetime.datetime.fromtimestamp(timestamp)
    except ValueError:
        # If that fails, try to interpret it as a datetime string
        format_str = '%Y-%m-%dT%H:%M:%S.%f'  # The format
        return datetime.datetime.strptime(input_string, format_str)



def run(cmd: str) -> None:
    """
    Execute a command and log any errors.

    :param cmd: the command to execute
    """
    general_log_file = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_log"
    try:
        ret = subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        dic_error = {"error": f'"error": "while trying to run command {cmd}, an error occurred: {e}"'}
        log_to_bot(dic_error, general_log_file)


def push_log(name_to_file: Dict):
    """
    push logs to remote bot server
    name_to_file:str:  a dictionary whose keys are the naming convention for files on the bot server and whose values are
     the paths to log files on the local. Note, the key is a relative path string and the value is an absolute path str
     current conventions: health_logs, general_logs

     Example:
             name_to_file = {
                "health_logs": security_log_file,
                "general_logs": general_log_file
            }

     """
    rsa_id_path = os.getenv('RSA_ID_PATH')
    remote_directory_path = os.getenv('REMOTE_PATH')  # user@host:path_to_directory

    if not rsa_id_path or not remote_directory_path:
        print(f'skipping push to remote. Set RSA_ID_PATH and REMOTE_PATH to send to remote.')
        return

    if not os.path.isfile(rsa_id_path):
        raise Exception(f"{rsa_id_path}, the rsa id path, does not exist")

    for saving_convention, log_file_path in name_to_file.items():
        file_name = f'{saving_convention}.{hostname}.json'
        temp_remote_path = os.path.join(remote_directory_path, file_name)
        # cmd = f'scp -i {rsa_id_path} {log_file_path} {temp_remote_path}'

        # Alternative transfer with rsync
        cmd = f'rsync -avz -e "ssh -i {rsa_id_path} -o StrictHostKeyChecking=no" {log_file_path} {temp_remote_path}'
        run(cmd)

        delete_entries_older_than_x_days(log_file_path)
