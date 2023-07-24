#!/usr/bin/python3
import sys

from dotenv import load_dotenv
load_dotenv()

# load this after settup up env variables
sys.path.append('..')
import telegram_bot.health_check as health_check

health_check. main()
