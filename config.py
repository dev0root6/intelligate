import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "intelligate-afc-secret-key-2024")
    DATABASE_DIR = os.path.join(BASE_DIR, "database")
    DATABASE_PATH = os.path.join(BASE_DIR, "database", "metro.db")
    FACES_DIR = os.path.join(BASE_DIR, "faces")
    UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Face distance threshold for face_recognition (128-d dlib embeddings).
    # Lower distance = closer match. Default dlib threshold is 0.60.
    # 0.50 provides strict, highly accurate matching to prevent misidentification.
    MAX_FACE_DISTANCE = float(os.environ.get("MAX_FACE_DISTANCE", "0.50"))

    # Minimum distance margin between 1st best match and 2nd best match.
    # If (second_best_distance - best_distance) < MIN_MATCH_MARGIN, the match is
    # considered ambiguous and rejected to avoid authorizing the wrong passenger.
    MIN_MATCH_MARGIN = float(os.environ.get("MIN_MATCH_MARGIN", "0.06"))

    # Legacy similarity threshold for pixel-correlation fallback (0.0 to 1.0)
    FACE_MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "0.45"))

    # ESP32 gate hardware settings (override via environment variables)
    ESP32_URL = os.environ.get("ESP32_URL", "http://10.216.156.204")
    ESP32_TIMEOUT = int(os.environ.get("ESP32_TIMEOUT", "5"))
