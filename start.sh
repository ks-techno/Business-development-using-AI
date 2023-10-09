#!/bin/bash

service redis-server start
python worker.py &
gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
