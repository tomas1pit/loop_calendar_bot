#!/usr/bin/env python3
"""
Script to initialize database and create tables
"""

from database import DatabaseManager
from config import Config

if __name__ == "__main__":
    db = DatabaseManager(Config.DB_PATH)
    print(f"Database initialized at {Config.DB_PATH}")
    db.close()
