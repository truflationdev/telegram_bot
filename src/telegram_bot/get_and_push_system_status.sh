#!/bin/bash
# This script should be run every 15 minutes to monitor the system

#todo -- this should be done in Python with error logging too

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT_DIR=$SCRIPT_DIR/..

#cd $ROOT_DIR
#
#echo "$ROOT_DIR"
#echo "$SCRIPT_DIR"
#exit 1

# remove since we are updating stage
$SCRIPT_DIR/health_check.py
$SCRIPT_DIR/push_logs_for_bot.py
