#!/bin/bash
source venv/bin/activate
python3 init_db.py
python3 import_data.py