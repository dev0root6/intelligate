"""Core business logic for IntelliGate AFC.

Face recognition strategy
-------------------------
Primary:  face_recognition library (128-d dlib embeddings).
          Install: pip install cmake dlib face_recognition
Fallback: Normalized Pearson pixel-correlation (no extra deps needed).
          Activates automatically if face_recognition is not installed.
"""

import os
import uuid
import base64
import secrets
import warnings
import numpy as np
from PIL import Image
from io import BytesIO
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from config import Config

# ---------------------------------------------------------------------------
# Optional face_recognition (dlib-based 128-d face embeddings)
# ---------------------------------------------------------------------------
try:
    import face_recognition as _fr
    _FR_AVAILABLE = True
except ImportError:
    _FR_AVAILABLE = False
    warnings.warn(
        "face_recognition is not installed — falling back to pixel-correlation.\n"
        "For accurate face matching install:  pip install cmake dlib face_recognition",
        RuntimeWarning,
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# Station list & fare constants — Namma Metro (Bengaluru), operational lines
# ---------------------------------------------------------------------------

# Stations per line, in travel order. Names are unique across the network;
# interchange stations (Majestic, Rashtreeya Vidyalaya Road) appear on both lines.
STATIONS_BY_LINE = {
    "Purple": [
        "Whitefield (Kadugodi)", "Hopefarm Channasandra", "Kadugodi Tree Park",
        "Pattandur Agrahara", "Sri Sathya Sai Hospital", "Nallurhalli",
        "Kundalahalli", "Seetharamapalya", "Hoodi", "Garudacharpalya",
        "Singayyanapalya", "Krishnarajapura", "Benniganahalli",
        "Baiyappanahalli", "Swami Vivekananda Road", "Indiranagar",
        "Halasuru", "Trinity", "Mahatma Gandhi Road", "Cubbon Park",
        "Vidhana Soudha", "Sir M. Visveshwaraya", "Nadaprabhu Kempegowda Stn., Majestic",
        "Krantiveera Sangolli Rayanna Railway Station", "Magadi Road",
        "Sri Balagangadharanatha Swamiji Stn., Hosahalli", "Vijayanagar",
        "Attiguppe", "Deepanjali Nagar", "Mysuru Road",
        "Pantharapalya - Nayandahalli", "Rajarajeshwari Nagar",
        "Jnanabharathi", "Pattanagere", "Kengeri Bus Terminal", "Kengeri",
        "Challaghatta",
    ],
    "Green": [
        "Madavara", "Chikkabidarakallu", "Manjunath Nagar", "Nagasandra",
        "Dasarahalli", "Jalahalli", "Peenya Industry", "Peenya",
        "Goraguntepalya", "Yeshwanthpur", "Sandal Soap Factory",
        "Mahalakshmi", "Rajajinagar", "Kuvempu Road", "Srirampura",
        "Mantri Square Sampige Road", "Nadaprabhu Kempegowda Stn., Majestic",
        "Chickpete", "Krishna Rajendra Market", "National College",
        "Lalbagh", "South End Circle", "Jayanagar",
        "Rashtreeya Vidyalaya Road", "Banashankari", "Jaya Prakash Nagar",
        "Yelachenahalli", "Konankunte Cross", "Doddakallasandra",
        "Vajarahalli", "Thalaghattapura", "Silk Institute",
    ],
    "Yellow": [
        "Rashtreeya Vidyalaya Road", "Ragigudda", "Jayadeva Hospital",
        "BTM Layout", "Central Silk Board", "Bommanahalli",
        "Hongasandra", "Kudlu Gate", "Singasandra", "Hosa Road",
        "Beratena Agrahara", "Electronic City",
        "Infosys Foundation Konappana Agrahara", "Huskur Road",
        "Biocon Hebbagodi", "Delta Electronics Bommasandra",
    ],
}

# Flat, alphabetically-sorted list of every station for dropdowns.
STATIONS = sorted({s for line in STATIONS_BY_LINE.values() for s in line})

# Station adjacency graph (undirected) with the line each edge belongs to.
_EDGES: dict = {}  # node -> {neighbor: line_name}
for _line, _stations in STATIONS_BY_LINE.items():
    for _a, _b in zip(_stations, _stations[1:]):
        _EDGES.setdefault(_a, {})[_b] = _line
        _EDGES.setdefault(_b, {})[_a] = _line

_ADJACENCY = {node: set(neighbors) for node, neighbors in _EDGES.items()}

BASE_FARE      = 10   # ₹ per passenger (minimum fare, ~1 station)
FARE_PER_STOP  = 2    # ₹ per additional stop per passenger
MAX_FARE       = 90   # ₹ per passenger (Namma Metro ticket cap)


def _stops_between(source: str, destination: str):
    """Shortest number of stops between two stations via BFS."""
    if source == destination:
        return 0
    if source not in _ADJACENCY or destination not in _ADJACENCY:
        return None
    from collections import deque
    visited = {source}
    queue = deque([(source, 0)])
    while queue:
        node, depth = queue.popleft()
        for nxt in _ADJACENCY.get(node, ()):
            if nxt == destination:
                return depth + 1
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return None  # unreachable


def shortest_route(source: str, destination: str):
    """Return the ordered list of stations on the shortest path, or None."""
    if source == destination:
        return [source]
    if source not in _EDGES or destination not in _EDGES:
        return None
    from collections import deque
    prev = {source: None}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if node == destination:
            break
        for nxt in _EDGES[node]:
            if nxt not in prev:
                prev[nxt] = node
                queue.append(nxt)
    if destination not in prev:
        return None
    path = []
    cur = destination
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return list(reversed(path))


def build_route_guide(source: str, destination: str):
    """Explain which metro lines to board (with interchanges) for a journey.

    Returns a dict with 'legs' (line, from, to, stops) and 'interchanges'
    (station, from_line, to_line), or None if no route exists.
    """
    path = shortest_route(source, destination)
    if not path or len(path) < 2:
        return None

    legs = []
    idx = 0
    while idx < len(path) - 1:
        line = _EDGES[path[idx]][path[idx + 1]]
        j = idx
        while j + 1 < len(path) and _EDGES[path[j]][path[j + 1]] == line:
            j += 1
        legs.append({
            "line": line,
            "from": path[idx],
            "to": path[j],
            "station_count": j - idx + 1,
            "stops": j - idx,
        })
        idx = j

    interchanges = [
        {
            "station": leg["to"],
            "from_line": legs[i]["line"],
            "to_line": legs[i + 1]["line"],
        }
        for i, leg in enumerate(legs[:-1])
    ]

    return {
        "source": source,
        "destination": destination,
        "total_stops": len(path) - 1,
        "legs": legs,
        "interchanges": interchanges,
    }


def calculate_fare(source: str, destination: str, passenger_count: int) -> float:
    """Return total fare (₹) for a journey.

    Fare = min(BASE_FARE + stops × FARE_PER_STOP, MAX_FARE) × passenger_count
    Stops are computed across the real Namma Metro network (with interchange).
    Example: Nagasandra → Jayanagar (Green Line, 16 stops), 2 pax
             = min(10 + 16×2, 90) × 2 = ₹42×2 = ₹84
    """
    stops = _stops_between(source, destination) or 0
    fare_per_pax = min(BASE_FARE + stops * FARE_PER_STOP, MAX_FARE)
    return round(fare_per_pax * passenger_count, 2)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    return check_password_hash(stored_hash, password)


# ---------------------------------------------------------------------------
# Face image persistence
# ---------------------------------------------------------------------------

def save_base64_face(image_data_url: str, booking_id: str, passenger_index: int):
    """Decode a base64 webcam snapshot and persist it as a 320×320 JPEG.

    Returns the filename (str) or None on failure.
    """
    if not image_data_url or "," not in image_data_url:
        return None
    _, encoded = image_data_url.split(",", 1)
    try:
        raw = base64.b64decode(encoded)
        img = Image.open(BytesIO(raw)).convert("RGB")
        img = img.resize((320, 320), Image.LANCZOS)
    except Exception:
        return None

    filename = f"{booking_id}_p{passenger_index}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join(Config.FACES_DIR, filename)
    img.save(filepath, "JPEG", quality=90)
    return filename


def list_face_images() -> list:
    """Return a list of all stored face image filenames."""
    if not os.path.exists(Config.FACES_DIR):
        return []
    return [
        f for f in os.listdir(Config.FACES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]


# ---------------------------------------------------------------------------
# Internal face helpers — pixel-correlation fallback
# ---------------------------------------------------------------------------

def _load_face_vec(filename: str):
    """Load a stored face image as a flattened greyscale numpy vector."""
    path = os.path.join(Config.FACES_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path).convert("L").resize((100, 100), Image.LANCZOS)
        return np.array(img, dtype=np.float32).flatten() / 255.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Internal face helpers (Primary: face_recognition dlib; Fallback: OpenCV Haar Cascade + 128-d Vector)
# ---------------------------------------------------------------------------

import logging
import cv2

logger = logging.getLogger("intelligate.face_rec")
logging.basicConfig(level=logging.INFO)

# OpenCV Haar Cascade Frontal Face Detector
_FACE_CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
_FACE_CASCADE = cv2.CascadeClassifier(_FACE_CASCADE_PATH)

# In-memory cache for 128-d face encodings (filename -> np.ndarray)
_ENCODING_CACHE = {}


def _encode_opencv_image(pil_or_np_img):
    """Detect facial region and extract a normalized 128-d feature vector using OpenCV.

    1. Detect face bounding box using OpenCV Haar Cascade.
    2. Crop to facial region (or central face crop fallback).
    3. Extract spatial texture and HSV color features (128 values).
    4. Return L2-normalized float32 vector.
    """
    try:
        if isinstance(pil_or_np_img, Image.Image):
            rgb = np.array(pil_or_np_img.convert("RGB"))
        else:
            rgb = pil_or_np_img

        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))

        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
            face_roi_bgr = bgr[y:y+h, x:x+w]
            face_roi_gray = gray[y:y+h, x:x+w]
        else:
            h_img, w_img = gray.shape
            cy, cx = h_img // 2, w_img // 2
            half_w = int(w_img * 0.35)
            half_h = int(h_img * 0.35)
            face_roi_bgr = bgr[max(0, cy-half_h):min(h_img, cy+half_h), max(0, cx-half_w):min(w_img, cx+half_w)]
            face_roi_gray = gray[max(0, cy-half_h):min(h_img, cy+half_h), max(0, cx-half_w):min(w_img, cx+half_w)]

        roi_bgr_128 = cv2.resize(face_roi_bgr, (128, 128), interpolation=cv2.INTER_AREA)
        roi_gray_128 = cv2.resize(face_roi_gray, (128, 128), interpolation=cv2.INTER_AREA)

        hsv = cv2.cvtColor(roi_bgr_128, cv2.COLOR_BGR2HSV)
        hist_h = cv2.calcHist([hsv], [0], None, [32], [0, 180]).flatten()
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256]).flatten()
        grid_8x8 = cv2.resize(roi_gray_128, (8, 8), interpolation=cv2.INTER_AREA).flatten().astype(np.float32)

        vec = np.concatenate([hist_h, hist_s, grid_8x8])
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
    except Exception as exc:
        logger.warning(f"[FACE_RECOG] OpenCV face encoding failed: {exc}")
        return None


def _get_stored_face_encoding(filename: str):
    """Retrieve or compute the 128-d face encoding for a stored passenger face image."""
    if filename in _ENCODING_CACHE:
        return _ENCODING_CACHE[filename]

    path = os.path.join(Config.FACES_DIR, filename)
    if not os.path.exists(path):
        return None

    if _FR_AVAILABLE:
        try:
            img = _fr.load_image_file(path)
            encs = _fr.face_encodings(img)
            enc = encs[0] if encs else None
            if enc is not None:
                _ENCODING_CACHE[filename] = enc
                return enc
        except Exception:
            pass

    # OpenCV fallback path
    try:
        pil_img = Image.open(path).convert("RGB")
        enc = _encode_opencv_image(pil_img)
        _ENCODING_CACHE[filename] = enc
        return enc
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core face comparison
# ---------------------------------------------------------------------------

def compare_faces(captured_data_url: str, max_distance: float = None):
    """Compare a live webcam frame against all stored passenger face images.

    Selects the best match using Euclidean face_distance (lower is closer).
    Enforces a strict maximum distance threshold and an ambiguity margin
    to ensure another passenger's ticket is NEVER authorized mistakenly.

    Args:
        captured_data_url: Base64-encoded JPEG data URL from the webcam.
        max_distance:      Maximum face_distance allowed (lower = stricter).
                           Defaults to Config.MAX_FACE_DISTANCE (0.50).

    Returns:
        (passenger_row, booking_row, similarity_score, reason_message)
    """
    if max_distance is None:
        max_distance = Config.MAX_FACE_DISTANCE

    min_margin = Config.MIN_MATCH_MARGIN

    if not captured_data_url or "," not in captured_data_url:
        return None, None, 0.0, "Invalid image data."

    # Decode incoming image frame
    try:
        _, encoded = captured_data_url.split(",", 1)
        raw = base64.b64decode(encoded)
        img_pil = Image.open(BytesIO(raw)).convert("RGB")
        img_rgb = np.array(img_pil)
    except Exception as exc:
        logger.error(f"[FACE_RECOG] Image decode error: {exc}")
        return None, None, 0.0, "Could not process captured image."

    db = get_db()
    passengers = db.execute(
        "SELECT * FROM passengers WHERE face_image_path IS NOT NULL AND ticket_status = 'Active'"
    ).fetchall()

    if not passengers:
        db.close()
        logger.info("[FACE_RECOG] No active passenger tickets found in database.")
        return None, None, 0.0, "No active passenger tickets found."

    # Extract encoding for captured frame
    captured_enc = None
    if _FR_AVAILABLE:
        try:
            encs = _fr.face_encodings(img_rgb)
            captured_enc = encs[0] if encs else None
        except Exception:
            captured_enc = None

    if captured_enc is None:
        # Fallback to OpenCV encoding
        captured_enc = _encode_opencv_image(img_pil)

    if captured_enc is None:
        db.close()
        logger.info("[FACE_RECOG] No face detected in webcam scan frame.")
        return None, None, 0.0, "No face detected in camera frame. Please center your face."

    # Calculate distance to all stored active passenger encodings
    candidates = []
    for p in passengers:
        stored_enc = _get_stored_face_encoding(p["face_image_path"])
        if stored_enc is None:
            continue
        dist = float(np.linalg.norm(stored_enc - captured_enc))
        candidates.append((dist, p))

    if not candidates:
        db.close()
        logger.warning("[FACE_RECOG] Could not generate encodings for stored passenger images.")
        return None, None, 0.0, "Face comparison failed — invalid stored passenger images."

    # Sort candidates by face distance ascending (lowest distance = best match)
    candidates.sort(key=lambda x: x[0])
    best_dist, best_passenger = candidates[0]
    similarity_score = round(max(0.0, 1.0 - (best_dist / 1.414)), 3)

    # Effective distance threshold
    eff_max_dist = max_distance if _FR_AVAILABLE else 0.40

    # 1. Check maximum distance threshold
    if best_dist > eff_max_dist:
        db.close()
        logger.info(
            f"[FACE_RECOG] REJECTED: Best candidate Passenger ID {best_passenger['id']} ({best_passenger['name']}) "
            f"distance {best_dist:.3f} > threshold {eff_max_dist:.3f}."
        )
        return None, None, similarity_score, "Face not recognized."

    # 2. Check ambiguity / multi-match margin between DIFFERENT passengers
    if len(candidates) > 1:
        # Find the next candidate that belongs to a DIFFERENT passenger/name
        diff_candidates = [c for c in candidates[1:] if c[1]["name"].strip().lower() != best_passenger["name"].strip().lower()]
        if diff_candidates:
            second_dist, second_passenger = diff_candidates[0]
            margin = second_dist - best_dist
            logger.info(
                f"[FACE_RECOG] Candidate #1: Passenger ID {best_passenger['id']} ({best_passenger['name']}), dist={best_dist:.3f}. "
                f"Candidate #2 (Different Person): Passenger ID {second_passenger['id']} ({second_passenger['name']}), dist={second_dist:.3f}, margin={margin:.3f}."
            )
            if margin < min_margin:
                db.close()
                logger.warning(
                    f"[FACE_RECOG] AMBIGUOUS MATCH DENIED: Distance margin ({margin:.3f}) between "
                    f"Passenger #{best_passenger['id']} ({best_passenger['name']}) and Passenger #{second_passenger['id']} ({second_passenger['name']}) "
                    f"is less than min_margin ({min_margin:.3f}). Denying entry to prevent misidentification."
                )
                return None, None, similarity_score, "Ambiguous face match — multiple passengers similar. Please use Backup Authentication."

    # Valid, unambiguous match!
    booking = db.execute(
        "SELECT * FROM bookings WHERE id = ?", (best_passenger["booking_id"],)
    ).fetchone()
    db.close()

    logger.info(
        f"[FACE_RECOG] SUCCESS MATCH: Passenger ID {best_passenger['id']} ({best_passenger['name']}), "
        f"Booking ID {booking['booking_id']}, distance={best_dist:.3f} (max={eff_max_dist:.3f})."
    )
    return best_passenger, booking, similarity_score, None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def get_user_by_email(email: str):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()
    return row


def get_user_by_id(user_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    return row


def create_user(full_name: str, email: str, phone: str, password: str) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (full_name, email, phone, password_hash) VALUES (?, ?, ?, ?)",
        (full_name, email, phone, hash_password(password)),
    )
    db.commit()
    user_id = cur.lastrowid
    db.close()
    return user_id


# ---------------------------------------------------------------------------
# Booking CRUD
# ---------------------------------------------------------------------------

def create_booking(
    user_id: int,
    source: str,
    destination: str,
    travel_date: str,
    passenger_count: int,
    passengers_data: list,
    fare: float,
) -> str:
    """Create a booking with associated passengers.

    Returns the public booking_id string (e.g. "MET4A9CF812B3").
    """
    booking_id = "MET" + secrets.token_hex(6).upper()

    db = get_db()
    cur = db.execute(
        "INSERT INTO bookings "
        "(booking_id, user_id, source, destination, travel_date, "
        " passenger_count, status, fare) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Active', ?)",
        (booking_id, user_id, source, destination, travel_date, passenger_count, fare),
    )
    booking_pk = cur.lastrowid

    for idx, p in enumerate(passengers_data):
        face_path = None
        if p.get("face_image"):
            face_path = save_base64_face(p["face_image"], booking_id, idx + 1)
        db.execute(
            "INSERT INTO passengers "
            "(booking_id, name, age, gender, face_image_path, ticket_status) "
            "VALUES (?, ?, ?, ?, ?, 'Active')",
            (booking_pk, p["name"], int(p["age"]), p["gender"], face_path),
        )

    db.commit()
    db.close()
    return booking_id


def get_booking_by_id(booking_id: str):
    db = get_db()
    row = db.execute(
        "SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)
    ).fetchone()
    db.close()
    return row


def get_passengers_by_booking(booking_pk: int):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM passengers WHERE booking_id = ?", (booking_pk,)
    ).fetchall()
    db.close()
    return rows


def get_user_bookings(user_id: int) -> list:
    """Return all bookings for a user, each entry includes the passenger list."""
    db = get_db()
    bookings = db.execute(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    result = []
    for b in bookings:
        passengers = db.execute(
            "SELECT * FROM passengers WHERE booking_id = ?", (b["id"],)
        ).fetchall()
        result.append({"booking": b, "passengers": passengers})
    db.close()
    return result


# ---------------------------------------------------------------------------
# Booking status management
# ---------------------------------------------------------------------------

def expire_old_bookings(user_id: int) -> int:
    """Auto-expire Active bookings whose travel_date has already passed.

    Also marks linked Active passengers as Expired.
    Returns the number of bookings expired in this call.
    """
    today = str(date.today())
    db = get_db()

    to_expire = db.execute(
        "SELECT id FROM bookings "
        "WHERE user_id = ? AND status = 'Active' AND travel_date < ?",
        (user_id, today),
    ).fetchall()

    count = 0
    for b in to_expire:
        db.execute(
            "UPDATE bookings SET status = 'Expired' WHERE id = ?", (b["id"],)
        )
        db.execute(
            "UPDATE passengers SET ticket_status = 'Expired' "
            "WHERE booking_id = ? AND ticket_status = 'Active'",
            (b["id"],),
        )
        count += 1

    if count:
        db.commit()
    db.close()
    return count


def cancel_booking(booking_id: str, user_id: int) -> bool:
    """Cancel an Active booking that belongs to user_id.

    Also transitions all linked Active passengers to Cancelled.
    Returns True on success, False if the booking is not found, not owned
    by this user, or is not in Active status.
    """
    db = get_db()
    booking = db.execute(
        "SELECT * FROM bookings WHERE booking_id = ? AND user_id = ?",
        (booking_id, user_id),
    ).fetchone()

    if not booking or booking["status"] != "Active":
        db.close()
        return False

    db.execute(
        "UPDATE bookings SET status = 'Cancelled' WHERE id = ?", (booking["id"],)
    )
    db.execute(
        "UPDATE passengers SET ticket_status = 'Cancelled' WHERE booking_id = ?",
        (booking["id"],),
    )
    db.commit()
    db.close()
    return True


def mark_passenger_entered(passenger_id: int) -> None:
    """Transition a passenger's ticket from Active → Entered."""
    db = get_db()
    db.execute(
        "UPDATE passengers "
        "SET ticket_status = 'Entered', entered_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (passenger_id,),
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Backup Gate Authentication (Booking Reference ID)
# ---------------------------------------------------------------------------

def get_booking_details_for_gate(booking_id: str) -> dict:
    """Fetch booking & passenger details for manual gate verification by Booking ID.

    Validates existence, travel date expiry, booking status, and passenger ticket status.
    """
    clean_id = (booking_id or "").strip().upper()
    if not clean_id:
        return {"status": "NotFound", "message": "Please enter a valid Booking Reference ID."}

    db = get_db()
    booking = db.execute(
        "SELECT * FROM bookings WHERE UPPER(booking_id) = ?", (clean_id,)
    ).fetchone()

    if not booking:
        db.close()
        return {"status": "NotFound", "message": f"No booking found for Reference ID '{clean_id}'."}

    today = str(date.today())

    # Check if travel date is expired
    if booking["travel_date"] < today:
        db.execute("UPDATE bookings SET status = 'Expired' WHERE id = ?", (booking["id"],))
        db.execute(
            "UPDATE passengers SET ticket_status = 'Expired' WHERE booking_id = ? AND ticket_status = 'Active'",
            (booking["id"],),
        )
        db.commit()

        b_dict = dict(booking)
        b_dict["status"] = "Expired"
        passengers = [dict(p) for p in db.execute("SELECT * FROM passengers WHERE booking_id = ?", (booking["id"],)).fetchall()]
        db.close()
        return {
            "status": "Expired",
            "message": "Ticket Expired — travel date has passed.",
            "booking": b_dict,
            "passengers": passengers,
        }

    passengers = [dict(p) for p in db.execute("SELECT * FROM passengers WHERE booking_id = ?", (booking["id"],)).fetchall()]
    b_dict = dict(booking)

    if b_dict["status"] == "Cancelled":
        db.close()
        return {
            "status": "Cancelled",
            "message": "This booking has been cancelled.",
            "booking": b_dict,
            "passengers": passengers,
        }

    # Check passenger statuses
    active_passengers = [p for p in passengers if p["ticket_status"] == "Active"]
    entered_passengers = [p for p in passengers if p["ticket_status"] == "Entered"]

    if not active_passengers and entered_passengers:
        db.close()
        return {
            "status": "Already Used",
            "message": "All passenger tickets for this booking have already been used.",
            "booking": b_dict,
            "passengers": passengers,
        }

    db.close()
    return {
        "status": "Valid",
        "message": f"Booking found with {len(active_passengers)} active passenger(s).",
        "booking": b_dict,
        "passengers": passengers,
    }


def manual_authorize_gate_entry(booking_id: str, passenger_id: int = None) -> tuple:
    """Manually authorize passenger entry via Booking ID.

    Returns (passenger, booking, error_message).
    """
    clean_id = (booking_id or "").strip().upper()
    db = get_db()

    booking = db.execute(
        "SELECT * FROM bookings WHERE UPPER(booking_id) = ?", (clean_id,)
    ).fetchone()

    if not booking:
        db.close()
        return None, None, "Booking Reference ID not found."

    if booking["travel_date"] < str(date.today()):
        db.close()
        return None, booking, "Ticket expired — travel date has passed."

    if booking["status"] == "Cancelled":
        db.close()
        return None, booking, "Booking is cancelled."

    if passenger_id is not None:
        passenger = db.execute(
            "SELECT * FROM passengers WHERE id = ? AND booking_id = ?",
            (passenger_id, booking["id"]),
        ).fetchone()
    else:
        passenger = db.execute(
            "SELECT * FROM passengers WHERE booking_id = ? AND ticket_status = 'Active' LIMIT 1",
            (booking["id"],),
        ).fetchone()

    if not passenger:
        db.close()
        return None, booking, "No active passenger available for entry."

    if passenger["ticket_status"] == "Entered":
        db.close()
        return passenger, booking, "Ticket already used for entry."

    # Mark as Entered
    db.execute(
        "UPDATE passengers SET ticket_status = 'Entered', entered_at = CURRENT_TIMESTAMP WHERE id = ?",
        (passenger["id"],),
    )
    db.commit()

    # Re-fetch updated row
    updated_passenger = db.execute("SELECT * FROM passengers WHERE id = ?", (passenger["id"],)).fetchone()
    db.close()

    return updated_passenger, booking, None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_user_stats(user_id: int) -> dict:
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS c FROM bookings WHERE user_id = ?", (user_id,)
    ).fetchone()["c"]
    active = db.execute(
        "SELECT COUNT(*) AS c FROM bookings WHERE user_id = ? AND status = 'Active'",
        (user_id,),
    ).fetchone()["c"]
    passengers = db.execute(
        "SELECT COUNT(*) AS c FROM passengers p "
        "JOIN bookings b ON p.booking_id = b.id WHERE b.user_id = ?",
        (user_id,),
    ).fetchone()["c"]
    db.close()
    return {
        "total_bookings": total,
        "active_bookings": active,
        "total_passengers": passengers,
    }

