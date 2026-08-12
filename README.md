# IntelliGate Automated Fare Collection (AFC) System using Facial Recognition

A complete web application that replaces QR-code ticket verification with facial recognition for metro transit.

## Features

- **User accounts** — register, login, logout, profile management
- **Ticket booking** — select source/destination, travel date, and 1–5 passengers
- **Face capture** — each passenger captures their face via the laptop webcam during booking
- **Booking confirmation** — unique Booking ID, travel + passenger details, Active status
- **My Bookings** — full history with per-passenger ticket status (Active / Entered / Expired)
- **Metro Gate Authentication** — continuous webcam scanning compares faces against stored passenger images and returns:
  - **Authorized** — matched passenger with a valid unused ticket (ticket marked Entered)
  - **Already Used** — matched passenger whose ticket is already Entered
  - **Unauthorized** — no matching passenger found

## Technology Stack

| Layer    | Technology |
|----------|------------|
| Frontend | HTML5, CSS3, Bootstrap 5, JavaScript |
| Backend  | Python Flask |
| Database | SQLite |
| Imaging  | Pillow, NumPy |

Everything runs locally. No cloud services, no paid APIs.

## Project Structure

```
.
├── app.py                 # Flask app factory + entry point
├── config.py              # Configuration (paths, secret key, thresholds)
├── database.py            # SQLite connection + schema initialization
├── services.py            # Auth, booking, and face-comparison logic
├── gate_controller.py     # Placeholder module for future ESP32 integration
├── routes.py              # All Flask routes (auth, booking, gate, API)
├── requirements.txt
├── README.md
├── database/              # SQLite database file (auto-created)
│   └── metro.db
├── faces/                 # Stored passenger face images (auto-created)
├── static/
│   ├── css/style.css
│   └── js/
│       ├── face_capture.js   # Webcam capture modal
│       ├── booking.js        # Dynamic passenger forms
│       └── gate.js           # Gate scanning loop
└── templates/
    ├── base.html
    ├── home.html
    ├── register.html
    ├── login.html
    ├── dashboard.html
    ├── book_ticket.html
    ├── confirmation.html
    ├── my_bookings.html
    ├── profile.html
    ├── gate.html
    └── error.html
```

## Database Schema

**users**
- id, full_name, email (unique), phone, password_hash, created_at

**bookings**
- id, booking_id (unique), user_id (FK), source, destination, travel_date, passenger_count, status, created_at

**passengers**
- id, booking_id (FK), name, age, gender, face_image_path, ticket_status, entered_at

A passenger belongs to one booking. Ticket status transitions: `Active` → `Entered` (on gate authorization) or `Expired`.

## ESP32 Integration (Future)

The backend is prepared for future ESP32 hardware integration via `gate_controller.py`. The ESP32 will only receive simple commands (`OPEN`, `CLOSE`, `STATUS`) — it does **not** perform face recognition. No firmware is included.

## Setup & Run

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

> Webcam access requires `https` or `localhost`. The app runs on `localhost` by default, so webcam capture works in modern browsers.

## How Face Matching Works

During booking, each passenger's webcam photo is saved as a 320×320 JPEG in `faces/`. At the gate, captured frames are converted to 100×100 grayscale, flattened to vectors, and compared against every stored face using normalized Pearson cross-correlation. A similarity score above the configured threshold (default 0.45) counts as a match. This is a lightweight, dependency-free approach suitable for demonstration; production deployments would use a dedicated face-embedding model.
