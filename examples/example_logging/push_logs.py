#!/usr/bin/python3
import sys

from dotenv import load_dotenv
load_dotenv()

# load this after settup up env variables
sys.path.append('..')
import telegram_bot.push_logs_for_bot as push_logs

push_logs.push_logs()
