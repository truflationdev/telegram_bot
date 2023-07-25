#!/usr/bin/python3
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.


"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""

import logging
import os
import time
import datetime
import subprocess
import json
import requests
import importlib

from telegram import __version__ as TG_VER
from collections import OrderedDict
from functools import wraps
from telegram_bot.utilities import str_to_datetime, load_logs_into_dict
from typing import List, Dict, Tuple, Callable, Union, Any

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ForceReply, Update, Bot
from telegram.ext import Application, CommandHandler, CallbackContext, ContextTypes, MessageHandler, filters

# # Enable logging
# logging.basicConfig(
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
# )
# logger = logging.getLogger(__name__)

# load_dotenv()
LOG_BOT_KEY = os.getenv('LOG_BOT_KEY')
my_chat_id = os.getenv('CHAT_ID')
my_heartbeat_chat_id = os.getenv('HEARTBEAT_CHAT_ID')
bot_directory = os.getenv('BOT_DIRECTORY')

# Get the name of the module from an environment variable
module_name = os.getenv('DAILY_FUNCTIONS_MODULE')

# Get the file path from the environment variable
heartbeat_wait_period_file = os.getenv('HEARTBEAT_WAIT_PERIOD_FILE')

required_vars = ['LOG_BOT_KEY', 'CHAT_ID', 'HEARTBEAT_CHAT_ID', 'BOT_DIRECTORY']
missing_vars = [var for var in required_vars if os.getenv(var) is None]

if missing_vars:
    missing_vars_str = ', '.join(missing_vars)
    raise Exception(f"Missing environment variables: {missing_vars_str}")

# todo -- possible error testing on this file
# Read the file and parse it into a dictionary
with open(heartbeat_wait_period_file, 'r') as f:
    heartbeat_wait_period_dic = json.load(f)

# todo -- have heartbeat cliff and wait time load from config file

# Dynamically import the module
daily_module = importlib.import_module(module_name) if module_name else None
# todo -- configure modules to load and be run via crontab setting (no need to run only once a day)

last_check_timestamp = 0
last_general_log_check_ts = 0

messages_created = []
heartbeat_start_time = int(time.time()) + 0  # start after some period to make testing lessing obnoxious

heartbeat_last_message_dic = dict({name: heartbeat_start_time for name in heartbeat_wait_period_dic.keys()})

# General Logs Keywords which send to Urgent chat versus heartbeat
alarm_words_for_general_logs = ["alert", "error"]


def admins_only(func: Callable) -> Callable:
    """
    Decorator to restrict access to admins only.

    :param func: The function to be decorated
    :return: The wrapped function that checks if the user is an admin before executing
    """

    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args: Any, **kwargs: Any) -> Union[None, Any]:
        """
        The wrapped function. Fetches the list of admins and checks if the user who sent the command is an admin.

        :param update: Incoming telegram update
        :param context: Context of the callback
        :param args: Additional arguments passed to the decorated function
        :param kwargs: Additional keyword arguments passed to the decorated function
        :return: The result of the decorated function if the user is an admin, None otherwise
        """
        # Fetch the list of admins in the chat
        admins = await context.bot.get_chat_administrators(my_chat_id)
        bot_info = await get_bot_info()

        # Get the user ids of the admins -- excluding the bot
        admin_ids = [admin.user.id for admin in admins if admin.user.id != bot_info.id]

        # Check if the user who sent the command is an admin
        user_id = update.message.from_user.id
        if user_id not in admin_ids:
            print(f'Unauthorized access attempt from user id: {id}')
            return  # If the user is not an admin, ignore the command

        return await func(update, context, *args, **kwargs)

    return wrapped


async def get_bot_info():
    """ gets info for this bot """
    # Create a Bot instance
    bot = Bot(token=LOG_BOT_KEY)  # replace 'YOUR_BOT_TOKEN' with your bot's API token

    # Use the getMe method to get information about the bot
    bot_info = await bot.getMe()

    return bot_info


def load_links():
    """ loads in an array of links from a file referenced in an environmental variable """
    links_file_path = os.getenv('LINKS_FILE_PATH')
    if not links_file_path:
        raise Exception('LINKS_FILE_PATH environment variable not set')

    try:
        with open(links_file_path, 'r') as file:
            links = json.load(file)
    except Exception as e:
        raise Exception(f'Error loading links from file at {links_file_path}: {e}')

    return links


links_to_check_uptime = load_links()


def check_values(timeseries_data: Dict, last_general_log_check_ts: float,
                 alarm_words_for_general_logs: List[str]) -> Tuple[str, str, float]:
    """
    Check the values of timeseries_data.

    :param timeseries_data: The timeseries data
    :param last_general_log_check_ts: The last check timestamp
    :param alarm_words_for_general_logs: A list of alarm words for general logs
    :return: A tuple containing the file logs, error logs, and the most recent timestamp
    """
    heartbeat_logs = ""
    error_logs = ""
    most_recent_timestamp = last_general_log_check_ts

    for time_string, data in timeseries_data.items():
        time_object = str_to_datetime(time_string)
        time_stamp = datetime.datetime.timestamp(time_object)

        if float(time_stamp) <= last_general_log_check_ts:
            continue
        elif float(time_stamp) > most_recent_timestamp:
            most_recent_timestamp = float(time_stamp)

        my_data_string = "\n".join(f'    {key}: {value}' for key, value in data.items() if key not in alarm_words_for_general_logs)
        if len(my_data_string):
            heartbeat_logs += f'  {time_object}:\n{my_data_string}\n'

        my_error_string = "\n".join(
            f'    {key}: {value}' for key, value in data.items() if key in alarm_words_for_general_logs)
        if len(my_error_string):
            error_logs += f'  {time_object}:\n{my_error_string}\n'

    return heartbeat_logs, error_logs, most_recent_timestamp


def get_files_given_key(bot_directory: str, name_key: str) -> List[str]:
    """
    Get all the general log files from the bot directory.

    :param bot_directory: The bot directory path
    :return: A list of file names
    """
    my_files = os.listdir(bot_directory)
    my_files = [x for x in my_files if name_key in x]
    return my_files


def get_alert_if_late(file_path: str) -> str:
    """ returns a string if not updated recently, or a empty string otherwise """
    last_updated = os.path.getmtime(file_path)
    ts_now = time.time()
    file_name = os.path.basename(file_path)
    my_alert_string = ""

    if ts_now - last_updated > 24 * 3600:  # Warning if not updated in an day
        my_alert_string = f'{file_name} has not been updated in {(ts_now - last_updated) // 3600} hours.\n'

    return my_alert_string


def process_general_log_files(bot_directory: str, my_files: List[str], last_general_log_check_ts: float,
                              alarm_words_for_general_logs: List[str]) -> Tuple[str, str, str, float]:
    """
    Process each general log file, extract the data, and check the values.

    :param bot_directory: The bot directory path
    :param my_files: A list of file names
    :param last_general_log_check_ts: The last check timestamp
    :param alarm_words_for_general_logs: A list of alarm words for general logs
    :return: A tuple containing the alert string, heartbeat messages, alarm messages, and the most recent timestamp
    """
    print(f'we are processing general log files....')
    my_alert_string = ""
    heartbeat_messages = ""
    alarm_messages = ""
    most_recent_timestamp_inner = last_general_log_check_ts
    most_recent_timestamp_outer = last_general_log_check_ts
    for file_name in my_files:
        file_path = os.path.join(bot_directory, file_name)
        server_name = ".".join(file_name.split(".json")[0].split(".")[1:])
        # todo -- we have removed the alert for general logs, as they are not meant to be periodic. However, ..
        # alert = get_alert_if_late(file_path)
        # if alert:
        #     alarm_messages += f'{server_name}:\n{alert}\n\n'

        print(f'processing file: {file_name}')

        timeseries_data = load_logs_into_dict(file_path)
        heartbeat_logs, error_logs, most_recent_timestamp_inner = check_values(timeseries_data, last_general_log_check_ts,
                                                                         alarm_words_for_general_logs)
        if heartbeat_logs:
            heartbeat_messages += f'{server_name}:\n{heartbeat_logs}\n\n'
        if error_logs:
            alarm_messages += f'{server_name}:\n{error_logs}\n\n'

        if most_recent_timestamp_inner > most_recent_timestamp_outer:
            most_recent_timestamp_outer = most_recent_timestamp_inner

        print(f'##  ')
        print(f'outer; inner; inner > outer')
        print(most_recent_timestamp_outer)
        print(most_recent_timestamp_inner)
        print(most_recent_timestamp_inner > most_recent_timestamp_outer)

    return my_alert_string, heartbeat_messages, alarm_messages, most_recent_timestamp_outer


async def send_heartbeat_and_alarm_messages(context: ContextTypes.DEFAULT_TYPE, heartbeat_messages: str,
                                            alarm_messages: str, heartbeat_type: str,
                                            my_chat_id: str, heartbeat_last_message_dic: Dict[str, int],
                                            heartbeat_wait_period_dic: Dict[str, int]) -> None:
    """
    Send the heartbeat and alarm messages.

    :param context: The bot context
    :param heartbeat_messages: The heartbeat messages
    :param alarm_messages: The alarm messages
    :param heartbeat_type: The type of heartbeat
    :param my_chat_id: The chat ID
    :param heartbeat_last_message_dic: The dictionary of last message timestamps
    :param heartbeat_wait_period_dic: The dictionary of wait periods
    """
    ts_now = int(time.time())

    # await print_to_heartbeat_chat(context, heartbeat_messages)

    if len(heartbeat_messages) > 0 and heartbeat_last_message_dic[heartbeat_type] + heartbeat_wait_period_dic.get(
            heartbeat_type, 24 * 3600) < ts_now:
        await print_to_heartbeat_chat(context, heartbeat_messages)
        heartbeat_last_message_dic[heartbeat_type] = ts_now

    if len(alarm_messages):
        await context.bot.send_message(chat_id=my_chat_id, text=f'{alarm_messages}')


async def check_general_logs(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Check general logs, process the files, and send heartbeat and alarm messages.

    :param context: ContextTypes.DEFAULT_TYPE The bot context
    :return: The alert string
    """
    global bot_directory, last_general_log_check_ts, alarm_words_for_general_logs, my_chat_id, heartbeat_last_message_dic, heartbeat_wait_period_dic

    print(f'check_general_logs ....')

    my_files = get_files_given_key(bot_directory, "general_logs")
    if not my_files:
        return f"no general_logs logs found\n"

    my_alert_string, heartbeat_messages, alarm_messages, most_recent_timestamp = process_general_log_files(
        bot_directory, my_files, last_general_log_check_ts, alarm_words_for_general_logs)

    print(f'\mcheck_general_logs almost finished -- ')
    print(f'most_recent_timestamp: {most_recent_timestamp}')
    print(f'--------------------------------------------------\n\n\n')

    if most_recent_timestamp > last_general_log_check_ts:
        last_general_log_check_ts = most_recent_timestamp

    await send_heartbeat_and_alarm_messages(context, heartbeat_messages, alarm_messages, "general_logs", my_chat_id,
                                            heartbeat_last_message_dic, heartbeat_wait_period_dic)

    return my_alert_string


#
#
# async def check_general_logs(context):
#     # get files
#     global bot_directory
#     global last_general_log_check_ts
#
#     my_files = os.listdir(bot_directory)
#     my_files = [x for x in my_files if "general_logs" in x]
#
#     if not len(my_files):
#         return f"no general_logs logs found\n"
#
#     alerts = []
#     my_alert_string = ""
#     my_records = dict()  # (date, value) pairs
#     heartbeat_messages = ""
#     alarm_messages = ""
#     most_recent_timestamp = last_general_log_check_ts
#
#     # process general logs files
#     for file_name in my_files:
#         last_updated = os.path.getmtime(os.path.join(bot_directory, file_name))
#         ts_now = time.time()
#         server_name = ".".join(file_name.split(".json")[0].split(".")[1:])
#
#         if ts_now - last_updated > 24*3600: # Warning if not updated in an day
#             my_alert_string += f'{file_name} has not been updated in { (ts_now - last_updated)//3600} hours.\n'
#
#         my_records[file_name] = dict()
#         try:
#             with open(os.path.join(bot_directory, file_name), 'r') as infile:
#                 json_data = infile.read()
#                 json_data = json_data if json_data else '{}'
#                 timeseries_data = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(json_data)
#         except Exception as e:
#             my_alert_string += f"Error with {file_name}: {e}\n"
#             continue
#
#         # check values via value_threshold_dict
#         file_logs = ""
#         error_logs = ""
#         for time_string, data in timeseries_data.items():
#             time_object = str_to_datetime(time_string)
#             time_stamp = datetime.datetime.timestamp(time_object)
#
#             if float(time_stamp) <= last_general_log_check_ts:
#                 continue
#             elif float(time_stamp) > most_recent_timestamp:
#                 most_recent_timestamp = float(time_stamp)
#             my_data_string = "\n".join(f'    {key}: {value}' for key, value in data.items())
#             if len(my_data_string):
#                 file_logs += f'  {time_object}:\n{my_data_string}\n'
#
#             my_error_string = "\n".join(f'    {key}: {value}' for key, value in data.items() if key in alarm_words_for_general_logs)
#             if len(my_error_string):
#                 error_logs += f'  {time_object}:\n{my_data_string}\n'
#
#         if len(file_logs):
#             heartbeat_messages += f'{server_name}:\n{file_logs}\n\n'
#         if len(error_logs):
#             alarm_messages += f'{server_name}:\n{error_logs}\n\n'
#
#     # send to heartbeat monitor, if time threshold has passed
#     ts_now = int(time.time())
#     last_general_log_check_ts = most_recent_timestamp
#
#     global heartbeat_last_message_dic
#     if len(heartbeat_messages) > 0 and heartbeat_last_message_dic["general_logs"] + heartbeat_wait_period_dic.get("general_logs", 24*3600) < ts_now:
#         await print_to_heartbeat_chat(context, heartbeat_messages)
#         heartbeat_last_message_dic["general_logs"] = ts_now
#
#     if len(alarm_messages):
#         ret = await context.bot.send_message(chat_id=my_chat_id, text=f'{alarm_messages}')
#
#     return my_alert_string


async def check_system_health(context: ContextTypes.DEFAULT_TYPE):
    # get files
    global bot_directory
    my_files = os.listdir(bot_directory)
    my_files = [x for x in my_files if "health_logs" in x]

    if not len(my_files):
        return f"no health_logs logs found\n"

    value_threshold_dict = {
        "disk_usage": 95,  # todo -- make updateable
    }

    alerts = []
    my_alert_string = ""
    global last_check_timestamp

    my_records = dict()  # (date, value) pairs
    heartbeat_messages = ""

    # process health files
    for file_name in my_files:

        last_updated = os.path.getmtime(os.path.join(bot_directory, file_name))
        ts_now = time.time()
        server_name = ".".join(file_name.split(".json")[0].split(".")[1:])

        if ts_now - last_updated > 3600:  # Warning if not updated in an hour
            my_alert_string += f'{file_name} has not been updated in {(ts_now - last_updated) // 3600} hours.\n'

        my_records[file_name] = dict()
        try:
            with open(os.path.join(bot_directory, file_name), 'r') as infile:
                json_data = infile.read()
                json_data = json_data if json_data else '{}'
                timeseries_data = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(json_data)
        except Exception as e:
            my_alert_string += f"Error with {file_name}: {e}\n"
            continue

        # convert times

        timeseries_data_copy = timeseries_data.copy()

        # check values via value_threshold_dict
        for time_object_str, data in timeseries_data_copy.items():
            # time_object = datetime.datetime.fromtimestamp(float(time_object_str)).isoformat(' ', 'seconds')
            time_object = str_to_datetime(time_object_str)
            time_stamp = datetime.datetime.timestamp(time_object)

            # del timestamps and only make datetimes
            del timeseries_data[time_object_str]
            timeseries_data[time_object] = data

            if float(time_stamp) < last_check_timestamp:
                continue
            for name, threshold in value_threshold_dict.items():
                if name in data:
                    if data[name] > threshold:
                        # if newer data
                        if name not in my_records or my_records[name][0] < time_stamp:
                            my_records[file_name][name] = (time_stamp, data[name])
                else:
                    my_alert_string = f'{file_name}: {name} not found.\n'

        # Get the most recent health data
        my_list = [(x, y) for (x, y) in timeseries_data.items()]
        # print(f'\n\nmy_list: \n {my_list}')
        latest_values_dict = [y for (x, y) in sorted(my_list, key=lambda x: x[0], reverse=True)][0]
        # print(f'\n\nlatest_values_dict: \n {latest_values_dict}')
        latest_values = "\n    ".join(f'{k}: {latest_values_dict[k]}' for k in value_threshold_dict.keys())
        # print(f'\n\nlatest_values: \n {latest_values}')
        heartbeat_messages += f'{server_name} ==>\n    {latest_values}\n'

    # # send to heartbeat monitor, if time threshold has passed
    # ts_now = int(time.time())
    # global heartbeat_last_message_dic
    # if heartbeat_last_message_dic["server_health_logs"] + heartbeat_wait_period_dic.get("server_health_logs",
    #                                                                                     24 * 3600) < ts_now:
    #     await print_to_heartbeat_chat(context, "Server Health Stats:\n\n" + heartbeat_messages)
    #     heartbeat_last_message_dic["server_health_logs"] = ts_now

    for file_name, records in my_records.items():
        for name, (ts, record) in records.items():
            server_name = ".".join(file_name.split(".json")[0].split(".")[1:])
            my_alert_string += f'{server_name} ==>  {name} ({record}) exceeds threshold ({value_threshold_dict[name]})\n'

    await send_heartbeat_and_alarm_messages(context, heartbeat_messages, my_alert_string, "server_health_logs",
                                            my_chat_id, heartbeat_last_message_dic, heartbeat_wait_period_dic)

    # return my_alert_string


# async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     """Echo the user message."""
#     print(update)
#     print(f'user: {update.message.from_user}')
#     print(f'user: {update.message}')
#     print(f'user: {update.message.chat.username}')
#     await update.message.reply_text(update.message.text)


async def print_to_heartbeat_chat(context: ContextTypes.DEFAULT_TYPE, heartbeat_message: str="beep beep") -> None:
    """Prints message to heartbeat_chat"""
    # await update.message.reply_text(my_message)
    if not heartbeat_message or not heartbeat_message.strip():
        return
    try:
        await context.bot.send_message(chat_id=my_heartbeat_chat_id, text=heartbeat_message, connect_timeout=20)
    except Exception as e:
        print(f'Error in print_to_heartbeat_chat: {e}. \n   Message: "{heartbeat_message}"')


# todo -- allow user to update ?
async def help_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Give info about commands."""
    help_message = '''
/help displays help messages
/start starts all jobs
/stop stops all jobs    
/reset resets log positions to 0    
/move_to_end moves log positions to end
/clear deletes bot messages from last start
/what_is_tracked gives details about what is tracked
/sleep pause all jobs. Example: /sleep d=7 h=1 m=5 s=30 
/jobs lists all scheduled jobs 
/run_jobs runs all tasks now -- doesn't affect scheduling 
    '''
    # await update.message.reply_text(help_message)
    await context.bot.send_message(chat_id=my_chat_id, text=help_message)


async def what_is_tracked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Give info about commands."""
    help_message = '''
    **** Frequencies may not be up to date *****
every 15 minutes > 
    • system health, including hard disk
every day after fetch >
    • errors in fetch logs
    • elements that should have been fetched but were not
    • errors in copying databases
'''
    if len(links_to_check_uptime):
        help_message += '''every 5 minutes > 
    • server up status for''' + "".join("\n        ‣ " + x for x in links_to_check_uptime)

    # await update.message.reply_text(help_message)
    await context.bot.send_message(chat_id=my_chat_id, text=help_message)


@admins_only
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset cursor position of logs."""
    global last_check_timestamp
    last_check_timestamp = 0
    # await update.message.reply_text("Resetting checked timestamp to 0")
    await context.bot.send_message(chat_id=my_chat_id, text="Resetting checked timestamp to 0")


@admins_only
async def move_to_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset cursor position of logs."""
    global last_check_timestamp
    ts = time.time()  # timestamp in seconds
    last_check_timestamp = ts
    # await update.message.reply_text("Resetting checked timestamp to end")
    await context.bot.send_message(chat_id=my_chat_id, text="Resetting checked timestamp to end")


@admins_only
async def delete_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """delete all messages of bot in chat."""
    global messages_created
    for chat_id, message_id in messages_created:
        await context.bot.delete_message(chat_id, message_id)


#
# async def check_system_health(context: ContextTypes.DEFAULT_TYPE):
#     # await context.bot.send_message(chat_id='504186992', text='One message every 3 seconds')
#     global last_check_timestamp
#     ts = time.time()  # timestamp in seconds
#
#     alerts = []
#     res = await check_health_logs(context)
#     if res:
#         new_mes = "There are issues with the health of the servers:\n\n" + res
#         alerts.append(new_mes)
#     last_check_timestamp = ts
#
#     if len(alerts):
#         for alert in alerts:
#             global messages_created
#             try:
#                 ret = await context.bot.send_message(chat_id=my_chat_id, text=f'{alert}')
#                 chat_id = ret.chat.id
#                 message_id = ret.message_id
#                 messages_created.append((chat_id, message_id))
#                 time.sleep(3)
#             except Exception as e:
#                 print(f'error in check_system_health:\n  {e}')
#
#     # heartbeat paused until there are greater diagnostics in system health (currently all logs are covered)
#     # ignore heartbeats for now
#     '''
#     ts_now = int(time.time())
#     global heartbeat_last_message_dic
#     if heartbeat_last_message_dic["system_health_check"] + heartbeat_wait_period_dic.get("check_system_health", 24*3600) < ts_now:
#         await print_to_heartbeat_chat(context, f"check_system_health finished")
#         heartbeat_last_message_dic["check_system_health"] = ts_now
#     '''


async def server_up_checks(context: ContextTypes.DEFAULT_TYPE):
    global links_to_check_uptime

    my_alert_string = ""
    heartbeat_message = ""

    successes = 0
    for link in links_to_check_uptime:
        try:
            response = requests.get(link, timeout=(5, 30))  # (connection, read)
            if response.status_code != 200:
                my_alert_string += f'{link} is down with error: {response.status_code}'
                heartbeat_message += f'  ❌  {link}\n'
            else:
                successes += 1
                heartbeat_message += f'  ✅  {link}\n'

        except Exception as e:
            my_alert_string += f'{link} not fetched. Exception:\n    {e}\n'
            heartbeat_message += f'  ❎ {link}\n'

    if my_alert_string:
        res = await context.bot.send_message(chat_id=my_chat_id, text=f'{my_alert_string}')

    ts_now = int(time.time())
    global heartbeat_last_message_dic
    if heartbeat_last_message_dic["up_checks"] + heartbeat_wait_period_dic.get("up_checks", 24 * 3600) < ts_now:
        heartbeat_message = f'{"✅" if successes == len(links_to_check_uptime) else "❎"}' \
                            + f' {successes}/{len(links_to_check_uptime)} URLs are up.\n\n' \
                            + heartbeat_message

        await print_to_heartbeat_chat(context, heartbeat_message)
        heartbeat_last_message_dic["up_checks"] = ts_now


@admins_only
async def get_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # job_names = [job.name for job in context.job_queue.jobs()]
    my_message = ""
    for job in context.job_queue.jobs():
        my_message += f'\n{"✅" if job.enabled else "❎"} {job.name} {f", at {job.next_t}" if job.next_t else ""}'
        # await update.message.reply_text(my_message)
    await context.bot.send_message(chat_id=my_chat_id, text=f'{my_message}')


@admins_only
async def run_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # job_names = [job.name for job in context.job_queue.jobs()]
    context_only_list = ["daily_checks", "check_system_health", "server_up_checks", "check_general_logs"]
    for job in context.job_queue.jobs():
        try:
            if job.name in context_only_list:
                res = await job.callback(context)
            else:
                res = await job.callback(update, context)
        except Exception as e:
            print(f'error in run_jobs: {e}')


async def daily_checks(context: ContextTypes.DEFAULT_TYPE):
    alerts = []
    heartbeat_messages = []

    if daily_module:
        alerts, heartbeat_messages = await daily_module.main(context)

    if len(alerts):
        global messages_created
        for alert in alerts:
            # buffer to size of 4k
            while len(alert) > 0:
                if len(alert) > 400:
                    chunk = alert[:4000]
                    alert = alert[4000:]
                else:
                    chunk = alert
                    alert = ""
                ret = await context.bot.send_message(chat_id=my_chat_id, text=f'{chunk}')
                chat_id = ret.chat.id
                message_id = ret.message_id
                messages_created.append((chat_id, message_id))
                time.sleep(3)

    ts_now = int(time.time())
    global heartbeat_last_message_dic
    if heartbeat_last_message_dic["daily_checks"] + heartbeat_wait_period_dic.get("daily_checks", 24 * 3600) < ts_now:
        heartbeat_message = f'Daily Checks Finished\n\n  • Duplication\n  • Fetch Error Logs\n  • Unfetched Check'
        await print_to_heartbeat_chat(context, heartbeat_message)
        heartbeat_last_message_dic["daily_checks"] = ts_now

        heartbeats_as_string = f"\n".join(msg for msg in heartbeat_messages)
        heartbeat_message = f'Custom heartbeat messages: \n\n  {heartbeats_as_string}'
        await print_to_heartbeat_chat(context, heartbeat_message)
        heartbeat_last_message_dic["daily_checks"] = ts_now


def main() -> None:
    # temp_insertion_for_testing()
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(LOG_BOT_KEY).read_timeout(30).write_timeout(30).build()
    job_queue = application.job_queue

    # time_to_check_fetch = datetime.time(hour=1, tzinfo=datetime.timezone.utc)
    utc_now = datetime.datetime.utcnow()
    next_time = utc_now.replace(hour=1, minute=0, second=0, microsecond=0)
    if not utc_now.hour == 0:
        next_time = next_time + datetime.timedelta(days=1)
    seconds_until_daily = int((next_time - utc_now).total_seconds())

    # todo -- update from json file
    job_monitor_system = job_queue.run_repeating(check_system_health, interval=60 * 60,
                                                 first=15)  # todo -- make updateable
    job_up_checks = job_queue.run_repeating(server_up_checks, interval=5 * 60, first=200)
    job_check_fetch_daily = job_queue.run_repeating(daily_checks, interval=24 * 60 * 60, first=seconds_until_daily)
    job_general_logs = job_queue.run_repeating(check_general_logs, interval=60, first=20)

    # Some bug seems to set these as false
    job_monitor_system.enabled = True
    job_check_fetch_daily.enabled = True
    job_up_checks.enabled = True
    job_general_logs.enabled = True

    if seconds_until_daily > 6 * 3600:
        job_queue.run_once(daily_checks, 3600)

    @admins_only
    async def start_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # await update.message.reply_text("Starting logs.")
        await context.bot.send_message(chat_id=my_chat_id, text="Starting logs.")
        await _start_logs(update)

    async def _start_logs(update: Update) -> None:
        job_monitor_system.enabled = True
        job_check_fetch_daily.enabled = True
        job_up_checks.enabled = True
        job_general_logs.enabled = True

        await job_check_fetch_daily.run(application)

    @admins_only
    async def stop_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if hasattr(update, "message") and "/stop" in update.message.text:
            args = update.message.text.split("/stop")[1].strip()
            args_list = args.split(" ")
        else:
            args_list = []

        if "non-daily" in args_list:
            reply = "Stopping all non-daily logs"
            job_monitor_system.enabled = False
            job_up_checks.enabled = False
        elif "up_check" in args_list:
            reply = "Stopping server-up checks."
            job_up_checks.enabled = False
        else:
            reply = "Stopping logs."
            job_monitor_system.enabled = False
            job_check_fetch_daily.enabled = False
            job_up_checks.enabled = False
            job_general_logs.enabled = False

        await context.bot.send_message(chat_id=my_chat_id, text=reply)

    @admins_only
    async def sleep_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # usage: /sleep d=1 h=2 m=3 s=4
        args = update.message.text.split("/sleep")[1].strip()

        args_list = args.split(" ")
        total_sleep = 0
        time_dict = dict({
            "s": 1,
            "seconds": 1,
            "m": 60,
            "minutes": 60,
            "h": 3600,
            "hours": 3600,
            "d": 86400,
            "days": 86400
        })

        if len(args_list):
            for _arg in args_list:
                if "=" not in _arg:
                    continue
                name, t = _arg.split("=")
                t = int(t) if t.isdigit() else 0
                total_sleep += time_dict.get(name, 0) * t

        # default to 1 day
        total_sleep = total_sleep if total_sleep else time_dict["d"]

        if total_sleep:
            #     remove existing jobs to restart
            # schedule_removal
            for job in context.job_queue.jobs():
                if job.name == "_start_logs":
                    job.schedule_removal()

            await stop_logs(update, context)
            wake_up_job = context.job_queue.run_once(_start_logs, total_sleep)
            wake_up_job.enabled = True

        ret = await context.bot.send_message(chat_id=my_chat_id, text=f'sleeping for {total_sleep} seconds')

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start_logs))
    application.add_handler(CommandHandler("stop", stop_logs))
    application.add_handler(CommandHandler("help", help_message))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("move_to_end", move_to_end))
    application.add_handler(CommandHandler("what_is_tracked", what_is_tracked))
    application.add_handler(CommandHandler("clear", delete_bot_messages))
    application.add_handler(CommandHandler("sleep", sleep_time))
    application.add_handler(CommandHandler("jobs", get_jobs))
    application.add_handler(CommandHandler("run_jobs", run_jobs))

    # on non command i.e message - echo the message on Telegram
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()

# Get grpup id by adding this bot to group:  @RawDataBot
