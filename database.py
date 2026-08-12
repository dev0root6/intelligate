import os
import sqlite3
from config import Config


def get_db():
    conn = sqlite3.connect(Config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(Config.DATABASE_DIR, exist_ok=True)
    os.makedirs(Config.FACES_DIR, exist_ok=True)
    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            travel_date TEXT NOT NULL,
            passenger_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            fare REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS passengers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            face_image_path TEXT,
            ticket_status TEXT NOT NULL DEFAULT 'Active',
            entered_at TIMESTAMP NULL,
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        )
        """
    )

    conn.commit()

    # Migration guard: add 'fare' to existing databases that were created
    # before this column was introduced.
    try:
        cur.execute("ALTER TABLE bookings ADD COLUMN fare REAL NOT NULL DEFAULT 0.0")
        conn.commit()
    except Exception:
        pass  # Column already exists — safe to ignore

    conn.close()
