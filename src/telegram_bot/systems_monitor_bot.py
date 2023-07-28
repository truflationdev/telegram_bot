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
from dotenv import load_dotenv

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

# Enable logging -- built into telegram python bot library
# logging.basicConfig(
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
# )
# logger = logging.getLogger(__name__)

load_dotenv()
LOG_BOT_KEY = os.getenv('LOG_BOT_KEY')
my_chat_id = os.getenv('CHAT_ID')
my_heartbeat_chat_id = os.getenv('HEARTBEAT_CHAT_ID')
bot_directory = os.getenv('BOT_DIRECTORY')

# Get the name of the module from an environment variable
module_name = os.getenv('DAILY_FUNCTIONS_MODULE')

# Get the file path from the environment variable
heartbeat_wait_period_file = os.getenv('HEARTBEAT_WAIT_PERIOD_FILE')

required_vars = ['LOG_BOT_KEY', 'CHAT_ID', 'HEARTBEAT_CHAT_ID', 'BOT_DIRECTORY', 'HEARTBEAT_WAIT_PERIOD_FILE']
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


def get_link_info():
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


        timeseries_data = load_logs_into_dict(file_path)
        heartbeat_logs, error_logs, most_recent_timestamp_inner = check_values(timeseries_data, last_general_log_check_ts,
                                                                         alarm_words_for_general_logs)
        if heartbeat_logs:
            heartbeat_messages += f'{server_name}:\n{heartbeat_logs}\n\n'
        if error_logs:
            alarm_messages += f'{server_name}:\n{error_logs}\n\n'

        if most_recent_timestamp_inner > most_recent_timestamp_outer:
            most_recent_timestamp_outer = most_recent_timestamp_inner

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

    my_files = get_files_given_key(bot_directory, "general_logs")
    if not my_files:
        return f"no general_logs logs found\n"

    my_alert_string, heartbeat_messages, alarm_messages, most_recent_timestamp = process_general_log_files(
        bot_directory, my_files, last_general_log_check_ts, alarm_words_for_general_logs)

    if most_recent_timestamp > last_general_log_check_ts:
        last_general_log_check_ts = most_recent_timestamp

    await send_heartbeat_and_alarm_messages(context, heartbeat_messages, alarm_messages, "general_logs", my_chat_id,
                                            heartbeat_last_message_dic, heartbeat_wait_period_dic)

    return my_alert_string


def get_most_recent_values(timeseries_data: Dict[str, Any], value_threshold_dict: Dict[str, int]) -> Dict[str, int]:
    """
    Get the most recent values from the time series data.

    :param timeseries_data: The time series data
    :param value_threshold_dict: The dictionary of value thresholds
    :return: A dictionary of the most recent values
    """

    # Convert the timeseries data into a list of tuples and sort it by time in descending order
    timeseries_data_list = sorted([(str_to_datetime(x), y) for (x, y) in timeseries_data.items()], reverse=True)

    # Get the data associated with the most recent timestamp
    latest_values_dict = timeseries_data_list[0][1] if timeseries_data_list else {}

    # Only keep the values that are in the value_threshold_dict
    latest_values_dict = {k: v for (k, v) in latest_values_dict.items() if k in value_threshold_dict}

    return latest_values_dict


def process_health_files(my_files: List[str], bot_directory: str, last_check_timestamp: float,
                         value_threshold_dict: Dict[str, int]) -> Tuple[str, str]:
    """
    Process each health file, extract the data, and check the values.

    :param my_files: A list of file names
    :param bot_directory: The bot directory path
    :param last_check_timestamp: The last check timestamp
    :param value_threshold_dict: A dictionary of value thresholds
    :return: A tuple containing an alert string and heartbeat messages
    """

    my_records = dict()  # (date, value) pairs
    my_alert_string = ""
    heartbeat_messages = ""

    for file_name in my_files:
        file_path = os.path.join(bot_directory, file_name)
        alert = get_alert_if_late(file_path)
        if alert:
            my_alert_string += alert

        my_records[file_name] = dict()
        timeseries_data = load_logs_into_dict(file_path)

        server_name = ".".join(file_name.split(".json")[0].split(".")[1:])

        # Get the most recent health data
        latest_values_dict = get_most_recent_values(timeseries_data, value_threshold_dict)
        # todo -- we can probably simplify the latest_values string creation
        latest_values = "\n    ".join(f'{k}: {latest_values_dict[k]}' for k in value_threshold_dict.keys() if k in latest_values_dict)

        for name, threshold in value_threshold_dict.items():
            if name in latest_values_dict:
                if latest_values_dict[name] > threshold:
                    my_alert_string += f'{server_name} ==>  {name} ({latest_values_dict[name]}) exceeds threshold ({value_threshold_dict[name]})\n'
            else:
                my_alert_string += f'{file_name}: {name} not found.\n'

        server_name = ".".join(file_name.split(".json")[0].split(".")[1:])
        heartbeat_messages += f'{server_name} ==>\n    {latest_values}\n'

    return my_alert_string, heartbeat_messages


async def check_system_health(context: ContextTypes.DEFAULT_TYPE):
    global last_check_timestamp
    my_files = get_files_given_key(bot_directory, "health_logs")
    if not len(my_files):
        return f"no health_logs logs found\n"

    value_threshold_dict = {
        "disk_usage": 95,  # todo -- make updateable
    }

    my_alert_string, heartbeat_messages = process_health_files(my_files, bot_directory,
                                                                           last_check_timestamp, value_threshold_dict)

    last_check_timestamp = time.time()

    await send_heartbeat_and_alarm_messages(context, heartbeat_messages, my_alert_string, "server_health_logs",
                                            my_chat_id, heartbeat_last_message_dic, heartbeat_wait_period_dic)


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
    links_to_check_uptime = get_link_info()

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


async def server_up_checks(context: ContextTypes.DEFAULT_TYPE):
    links_to_check_uptime = get_link_info()

    # skip checking and reporting if no links to check
    if not len(links_to_check_uptime):
        return

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
