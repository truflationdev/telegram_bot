#!/usr/bin/python3
import shutil
import time
import json
import os

from collections import OrderedDict
from dotenv import load_dotenv
from utitlties import delete_entries_older_than_x_days, load_logs_into_dict, save_logs, log_to_bot


load_dotenv()
log_file_path = os.getenv('SECURITY_LOGFILE')


def get_disk_usage():
    # Path
    path = "/"

    # Get the disk usage statistics
    stat = shutil.disk_usage(path)

    disk_usage = round(stat.used/stat.total*100, 2)
    return {"disk_usage": disk_usage}


def main():
    # create a dictionary of data_name: value pairs
    data_dict = get_disk_usage()

    log_to_bot(data_dict, log_file_path)


if __name__ == '__main__':
    main()
    delete_entries_older_than_x_days(log_file_path)

