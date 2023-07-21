#!/usr/bin/env python3
"""
Usage:
  this_script.py JSON_ARG

Options:

Arguments:
  JSON_ARG    JSON argument to log
"""

# to clear all logs
# python3 -c 'import general_logger; general_logger.delete_entries_older_than_x_days(0)'

import json
import os
from dotenv import load_dotenv
import docopt
import datetime
from telegram_bot.utilities import delete_entries_older_than_x_days, save_logs, load_logs_into_dict, log_to_bot
import telegram_bot.utilities

# load_dotenv()
# log_file_path = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_logfile"
# log_life = int(os.getenv('LOG_LIFE') if os.getenv('LOG_LIFE') else 3)


def log_to_bot(my_json_arg: str) -> None:
    """
    Main function to process the JSON argument and save the logs.

    :param my_json_arg: the JSON argument to process
    """
    log_file_path = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_logfile"
    telegram_bot.utilities.log_to_bot(my_json_arg, log_file_path)


if __name__ == '__main__':
    args = docopt.docopt(__doc__)
    my_json_arg = args.get("JSON_ARG", None)
    log_file_path = os.getenv('GENERAL_LOGFILE') if os.getenv('GENERAL_LOGFILE') else "telegram_bot_general_logfile"
    log_life = int(os.getenv('LOG_LIFE') if os.getenv('LOG_LIFE') else 3)

    telegram_bot.utilities.log_to_bot(my_json_arg, log_file_path)
    delete_entries_older_than_x_days(log_file_path, log_life)
