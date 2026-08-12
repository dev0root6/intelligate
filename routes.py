"""Flask route definitions for IntelliGate AFC.

All application routes live here.  Import order matters:
  routes → services → database → config
"""

import threading
import functools
from datetime import date
from flask import (
    render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
from services import (
    STATIONS, calculate_fare,
    verify_password, create_user, get_user_by_email, get_user_by_id,
    create_booking, get_user_bookings, get_user_stats,
    compare_faces, mark_passenger_entered,
    expire_old_bookings, cancel_booking,
    get_booking_details_for_gate, manual_authorize_gate_entry,
    build_route_guide, estimate_distance_km, namma_metro_fare,
)
from config import Config


def register_routes(app):

    # ------------------------------------------------------------------ helpers

    def login_required(view):
        """Decorator that redirects unauthenticated users to the login page."""
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def current_user():
        """Return the logged-in User row, or None."""
        if "user_id" not in session:
            return None
        return get_user_by_id(session["user_id"])

    # Expose helpers to all Jinja2 templates
    app.jinja_env.globals["current_user"] = current_user
    app.jinja_env.globals["STATIONS"] = STATIONS

    # ------------------------------------------------------------------ face image serving

    @app.route("/faces/<path:filename>")
    def serve_face(filename):
        """Serve passenger face images stored in the faces/ directory.

        Flask's url_for('static', ...) cannot serve files outside the static/
        folder, so we use a dedicated route backed by send_from_directory.
        """
        return send_from_directory(Config.FACES_DIR, filename)

    # ------------------------------------------------------------------ auth routes

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email     = request.form.get("email", "").strip().lower()
            phone     = request.form.get("phone", "").strip()
            password  = request.form.get("password", "")
            confirm   = request.form.get("confirm_password", "")

            if not all([full_name, email, phone, password, confirm]):
                flash("All fields are required.", "danger")
                return redirect(url_for("register"))
            if password != confirm:
                flash("Passwords do not match.", "danger")
                return redirect(url_for("register"))
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "danger")
                return redirect(url_for("register"))
            if get_user_by_email(email):
                flash("An account with this email already exists.", "danger")
                return redirect(url_for("register"))

            create_user(full_name, email, phone, password)
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email    = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            user = get_user_by_email(email)
            if not user or not verify_password(user["password_hash"], password):
                flash("Invalid email or password.", "danger")
                return redirect(url_for("login"))

            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("home"))

    # ------------------------------------------------------------------ dashboard

    @app.route("/dashboard")
    @login_required
    def dashboard():
        # Auto-expire any past bookings for this user before computing stats
        expire_old_bookings(session["user_id"])

        stats  = get_user_stats(session["user_id"])
        recent = get_user_bookings(session["user_id"])[:3]
        return render_template("dashboard.html", stats=stats, recent=recent)

    # ------------------------------------------------------------------ book ticket

    @app.route("/book-ticket", methods=["GET", "POST"])
    @login_required
    def book_ticket():
        if request.method == "POST":
            source          = request.form.get("source", "")
            destination     = request.form.get("destination", "")
            travel_date     = request.form.get("travel_date", "")
            passenger_count = int(request.form.get("passenger_count", 1))

            if source == destination:
                flash("Source and destination cannot be the same.", "danger")
                return redirect(url_for("book_ticket"))

            # Bug fix: reject past travel dates
            if travel_date < str(date.today()):
                flash("Travel date cannot be in the past.", "danger")
                return redirect(url_for("book_ticket"))

            passengers_data = []
            for i in range(passenger_count):
                name   = request.form.get(f"p{i}_name", "").strip()
                age    = request.form.get(f"p{i}_age", "").strip()
                gender = request.form.get(f"p{i}_gender", "")
                face   = request.form.get(f"p{i}_face", "")

                if not name or not age or not gender:
                    flash(f"Passenger {i + 1} details are incomplete.", "danger")
                    return redirect(url_for("book_ticket"))
                if not face:
                    flash(f"Please capture a face photo for passenger {i + 1}.", "danger")
                    return redirect(url_for("book_ticket"))

                passengers_data.append({
                    "name": name, "age": age, "gender": gender, "face_image": face,
                })

            # Calculate station-distance based fare
            fare = calculate_fare(source, destination, passenger_count)

            booking_id = create_booking(
                session["user_id"], source, destination, travel_date,
                passenger_count, passengers_data, fare,
            )
            flash(f"Booking confirmed! Your Booking ID is {booking_id}", "success")
            return redirect(url_for("booking_confirmation", booking_id=booking_id))

        return render_template("book_ticket.html", stations=STATIONS)

    @app.route("/booking-confirmation/<booking_id>")
    @login_required
    def booking_confirmation(booking_id):
        db = get_db()
        booking = db.execute(
            "SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)
        ).fetchone()

        if not booking or booking["user_id"] != session["user_id"]:
            db.close()
            flash("Booking not found.", "danger")
            return redirect(url_for("my_bookings"))

        passengers = db.execute(
            "SELECT * FROM passengers WHERE booking_id = ?", (booking["id"],)
        ).fetchall()
        db.close()
        route_guide = build_route_guide(booking["source"], booking["destination"])
        return render_template(
            "confirmation.html",
            booking=booking,
            passengers=passengers,
            route_guide=route_guide,
        )

    # ------------------------------------------------------------------ my bookings

    @app.route("/my-bookings")
    @login_required
    def my_bookings():
        # Auto-expire past bookings before displaying
        expire_old_bookings(session["user_id"])
        bookings = get_user_bookings(session["user_id"])
        return render_template("my_bookings.html", bookings=bookings)

    # ------------------------------------------------------------------ cancel booking

    @app.route("/cancel-booking/<booking_id>", methods=["POST"])
    @login_required
    def cancel_booking_route(booking_id):
        """Cancel an Active booking and all its passenger tickets."""
        success = cancel_booking(booking_id, session["user_id"])
        if success:
            flash("Booking cancelled successfully.", "success")
        else:
            flash(
                "Could not cancel booking — it may already be cancelled or expired.",
                "warning",
            )
        return redirect(url_for("my_bookings"))

    # ------------------------------------------------------------------ profile

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user  = get_user_by_id(session["user_id"])
        stats = get_user_stats(session["user_id"])

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone     = request.form.get("phone", "").strip()
            db = get_db()
            db.execute(
                "UPDATE users SET full_name = ?, phone = ? WHERE id = ?",
                (full_name, phone, session["user_id"]),
            )
            db.commit()
            db.close()   # Bug fix: was leaking a connection on every save
            flash("Profile updated successfully.", "success")
            return redirect(url_for("profile"))

        return render_template("profile.html", user=user, stats=stats)

    # ------------------------------------------------------------------ plan route

    @app.route("/plan-route")
    def plan_route():
        """Public route & fare planner — no login required."""
        return render_template("plan_route.html", stations=STATIONS)

    @app.route("/api/plan-route", methods=["POST"])
    def plan_route_api():
        """Public API: plan a journey and get the fare per Namma Metro pricing."""
        data = request.get_json(silent=True) or {}
        source = (data.get("source") or "").strip()
        destination = (data.get("destination") or "").strip()
        try:
            passenger_count = int(data.get("passenger_count") or 1)
        except (TypeError, ValueError):
            passenger_count = 1
        passenger_count = max(1, min(passenger_count, 5))

        if not source or not destination:
            return jsonify({"status": "Error", "message": "Please select both stations."}), 400
        if source == destination:
            return jsonify({"status": "Error", "message": "Source and destination cannot be the same."}), 400

        guide = build_route_guide(source, destination)
        if guide is None:
            return jsonify({"status": "Error", "message": "No route found between these stations."}), 400

        km = estimate_distance_km(source, destination)
        fare_per_pax = namma_metro_fare(km)
        return jsonify({
            "status": "OK",
            "guide": guide,
            "distance_km": km,
            "fare_per_pax": fare_per_pax,
            "fare": round(fare_per_pax * passenger_count, 2),
            "passenger_count": passenger_count,
        })

    # ------------------------------------------------------------------ metro gate

    @app.route("/gate")
    def gate():
        return render_template("gate.html")

    @app.route("/api/gate/verify", methods=["POST"])
    def gate_verify():
        """Public API endpoint for gate face verification.

        Intentionally unauthenticated so a standalone kiosk can call it
        without maintaining a user session.
        """
        data  = request.get_json(silent=True) or {}
        image = data.get("image")

        if not image:
            return jsonify({"status": "Error", "message": "No image provided."}), 400

        passenger, booking, score, reason = compare_faces(image)

        if passenger is None:
            return jsonify({
                "status": "Unauthorized",
                "message": reason or "Face not recognized. Please try again or use Backup Authentication.",
                "similarity": round(score, 3),
            })

        # Check booking-level date expiry (belt-and-suspenders)
        if booking and booking["travel_date"] < str(date.today()):
            return jsonify({
                "status": "Expired",
                "message": "Ticket expired — travel date has already passed.",
                "passenger_name": passenger["name"],
                "booking_id":     booking["booking_id"],
            })

        ticket_status = passenger["ticket_status"]

        if ticket_status == "Entered":
            return jsonify({
                "status":         "Already Used",
                "message":        "This ticket has already been used for entry.",
                "passenger_name": passenger["name"],
                "booking_id":     booking["booking_id"] if booking else None,
            })

        if ticket_status in ("Expired", "Cancelled"):
            return jsonify({
                "status":         "Expired",
                "message":        f"This ticket is {ticket_status.lower()}.",
                "passenger_name": passenger["name"],
                "booking_id":     booking["booking_id"] if booking else None,
            })

        # ---- Authorized: mark Entered + trigger ESP32 gate open ----
        mark_passenger_entered(passenger["id"])

        def _open_gate_async():
            """Non-blocking ESP32 gate command — runs in a daemon thread."""
            try:
                from gate_controller import send_gate_command
                send_gate_command("OPEN")
            except Exception:
                pass  # ESP32 unreachable — UI still shows Authorized

        threading.Thread(target=_open_gate_async, daemon=True).start()

        return jsonify({
            "status":         "Authorized",
            "message":        "Entry authorized. Gate opening...",
            "passenger_name": passenger["name"],
            "booking_id":     booking["booking_id"] if booking else None,
            "similarity":     round(score, 3),
        })

    @app.route("/api/gate/lookup", methods=["POST"])
    def gate_lookup():
        """Public API endpoint to lookup booking details by Booking Reference ID."""
        data = request.get_json(silent=True) or {}
        booking_id = data.get("booking_id", "").strip()

        if not booking_id:
            return jsonify({"status": "Error", "message": "Booking Reference ID is required."}), 400

        result = get_booking_details_for_gate(booking_id)
        return jsonify(result)

    @app.route("/api/gate/manual-authorize", methods=["POST"])
    def gate_manual_authorize():
        """Public API endpoint to manually authorize entry via Booking Reference ID."""
        data = request.get_json(silent=True) or {}
        booking_id = data.get("booking_id", "").strip()
        passenger_id = data.get("passenger_id")

        if not booking_id:
            return jsonify({"status": "Error", "message": "Booking Reference ID is required."}), 400

        passenger, booking, error_msg = manual_authorize_gate_entry(booking_id, passenger_id)

        if error_msg:
            return jsonify({
                "status": "Unauthorized",
                "message": error_msg,
                "booking_id": booking["booking_id"] if booking else booking_id,
            })

        # Trigger async ESP32 gate open
        def _open_gate_async():
            try:
                from gate_controller import send_gate_command
                send_gate_command("OPEN")
            except Exception:
                pass

        threading.Thread(target=_open_gate_async, daemon=True).start()

        return jsonify({
            "status": "Authorized",
            "message": "Entry authorized via Booking Reference ID. Gate opening...",
            "passenger_name": passenger["name"],
            "booking_id": booking["booking_id"],
        })

    # ------------------------------------------------------------------ error handlers

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500, message="Something went wrong"), 500
