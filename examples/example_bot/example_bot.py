#!/usr/bin/python3
import sys

from dotenv import load_dotenv
load_dotenv()

# load this after settup up env variables
sys.path.append('..')
import telegram_bot.systems_monitor_bot as t_bot

t_bot.main()
