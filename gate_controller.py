"""ESP32 gate hardware interface.

The ESP32 exposes a simple HTTP endpoint that accepts OPEN / CLOSE / STATUS
commands.  This module is called asynchronously from routes.py after a
successful gate authorization to physically open the turnstile.

Override the ESP32 address at runtime via the ESP32_URL environment variable:
    ESP32_URL=http://10.216.156.204 python app.py
"""

import requests
from config import Config


def send_gate_command(command: str):
    """Send a command to the ESP32 gate controller.

    Args:
        command: One of 'OPEN', 'CLOSE', or 'STATUS'.

    Returns:
        The ESP32 response text on success, or a dict with an 'error' key
        if the hardware is unreachable.
    """
    try:
        resp = requests.post(
            f"{Config.ESP32_URL}/gate",
            json={"command": command},
            timeout=Config.ESP32_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        return {"error": str(exc), "command": command}
