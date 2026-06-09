import serial
import serial.tools.list_ports
import time
import datetime


# ─────────────────────────────────────────────────────────────────────────────
# TIME SETUP
# Current time: Tuesday, June 09, 2026, Eastern Standard Time (UTC-5)
# The script sets the RTC to this value automatically — no manual key-press
# needed.  Update NOW to the current time before running.
# ─────────────────────────────────────────────────────────────────────────────
NOW = datetime.datetime.now()           # Uses the PC clock at script start;
                                        # override with a literal if preferred:
                                        # datetime.datetime(2026, 6, 9, 15, 30, 0)
UTC_OFFSET = "-5"                       # Eastern Standard Time


# ─────────────────────────────────────────────────────────────────────────────
# BAUD RATES
# The OLA boots and presents its menu at 115200 bps by default.
# We open at 115200, change the baud rate to 230400 inside the menu,
# then the OLA freezes and waits.  We close the port, reopen at 230400,
# reset the board via DTR toggle, and continue the remaining commands.
# ─────────────────────────────────────────────────────────────────────────────
TARGET_BAUD = 230400


# ─────────────────────────────────────────────────────────────────────────────
# MENU NAVIGATION NOTES
#
# Main menu:
#   1 → Configure Terminal Output   (log rate, baud rate)
#   2 → Configure Time Stamp        (RTC date / time / UTC offset)
#   3 → Configure IMU Logging
#   5 → Configure Analog Logging
#   x → Exit / save & restart
#
# Date format:
#   The OLA serial menu only exposes MM/DD/YYYY (default) and DD/MM/YYYY
#   (option 5 in the Time Stamp menu).  yyyy/mm/dd is not available via
#   the serial menu and would require a firmware change.  The RTC stores
#   the date correctly regardless of display format.
#
# Sample rate:
#   The OLA sets a *target* rate.  Actual throughput is typically 5–10 Hz
#   below the configured value (~90–95 Hz for a 100 Hz target).  Acceptable.
#
# IMU toggles:
#   Gyro / mag / temp options are TOGGLES, not set-to-value commands.
#   This script assumes factory-default state: gyro ON, mag ON, temp ON.
#   Each toggle is sent once to turn it OFF.  If a board was already
#   partially configured, verify its state before running.
# ─────────────────────────────────────────────────────────────────────────────


def send(ser: serial.Serial, payload: bytes, delay: float, step: int):
    """Write payload, wait, read response, print."""
    ser.write(payload)
    time.sleep(delay)
    response = ser.read_all().decode(errors='ignore').strip()
    label = payload.decode(errors='ignore').strip() or '<CR>'
    if response:
        print(f"  [{step:02d}] ← {label!r:12s}  »  {response[:120]}")
    else:
        print(f"  [{step:02d}] ← {label!r:12s}  »  (no response)")
    return response


def configure_board(port_name: str):
    """Configure one OLA board in two serial passes (boot baud, then target baud)."""
    print(f"\n{'═'*60}")
    print(f"  Configuring: {port_name}")
    print(f"{'═'*60}")

    # Capture time *right now* so the RTC is set as accurately as possible.
    t = datetime.datetime.now()
    year_2d = f"{t.year % 100:02d}"
    month   = f"{t.month:02d}"
    day     = f"{t.day:02d}"
    hour    = f"{t.hour:02d}"
    minute  = f"{t.minute:02d}"
    second  = f"{t.second:02d}"

    step = 0

    # ═══════════════════════════════════════════════════════════════════
    # PASS 1 — boot baud (115200): set time/date and change baud rate
    # ═══════════════════════════════════════════════════════════════════
    try:
        with serial.Serial(port_name, 230400, timeout=2) as ser:
            time.sleep(1.5)   # Let board finish its startup print

            # Open main menu
            step += 1; send(ser, b'\r',          1.0, step)

            # ── Time Stamp menu (main menu → 2) ───────────────────────
            step += 1; send(ser, b'2\r',          0.5, step)

            # Set date (option 4): year, month, day
            step += 1; send(ser, b'4\r',          0.5, step)
            step += 1; send(ser, f"{year_2d}\r".encode(), 0.4, step)
            step += 1; send(ser, f"{month}\r".encode(),   0.4, step)
            step += 1; send(ser, f"{day}\r".encode(),     0.5, step)

            # Set time (option 6): hour (24h), minute, second
            step += 1; send(ser, b'6\r',          0.5, step)
            step += 1; send(ser, f"{hour}\r".encode(),   0.4, step)
            step += 1; send(ser, f"{minute}\r".encode(), 0.4, step)
            step += 1; send(ser, f"{second}\r".encode(), 0.5, step)

            # UTC offset (option 9)
            step += 1; send(ser, b'9\r',          0.5, step)
            step += 1; send(ser, f"{UTC_OFFSET}\r".encode(), 0.5, step)

            # Exit Time Stamp menu → back to main menu
            step += 1; send(ser, b'x\r',          0.5, step)

            # ── Terminal Output menu (main menu → 1) ──────────────────
            #    Change baud rate LAST in this pass; board freezes after.
            step += 1; send(ser, b'1\r',          0.5, step)
            step += 1; send(ser, b'3\r',          0.5, step)   # option 3: baud rate
            step += 1; send(ser, f"{TARGET_BAUD}\r".encode(), 1.5, step)
            # Board now prints "Freezing..." and waits for reconnect at new baud.

        print(f"\n  ⏳  Baud changed to {TARGET_BAUD}. Resetting board and reconnecting...")
        time.sleep(2.0)   # Give the board time to fully freeze / settle

    except Exception as exc:
        print(f"\n  ❌  Pass 1 failed on {port_name}: {exc}")
        return

    # ═══════════════════════════════════════════════════════════════════
    # PASS 2 — target baud (230400): log rate, analog, IMU
    # Toggle DTR to reset the board so it boots fresh at the new baud.
    # ═══════════════════════════════════════════════════════════════════
    try:
        with serial.Serial(port_name, TARGET_BAUD, timeout=2) as ser:
            # DTR reset pulse (bootloader circuit)
            ser.dtr = False
            time.sleep(0.1)
            ser.dtr = True
            time.sleep(2.0)   # Wait for board to boot and print startup text

            # Open main menu
            step += 1; send(ser, b'\r',    1.0, step)

            # ── Terminal Output menu (main menu → 1) ──────────────────
            #    Set log rate to 100 Hz (option 4)
            step += 1; send(ser, b'1\r',   0.5, step)
            step += 1; send(ser, b'4\r',   0.5, step)   # option 4: log rate (Hz)
            step += 1; send(ser, b'100\r', 0.5, step)   # 100 Hz target
            step += 1; send(ser, b'x\r',   0.5, step)   # exit Terminal Output

            # ── Analog Logging menu (main menu → 5) ───────────────────
            #    Enable pin 32 (microphone ENVELOPE, 2V max)  → option 1
            #    Raw ADC output  → option 5 (toggles voltage ↔ raw ADC)
            step += 1; send(ser, b'5\r',   0.5, step)
            step += 1; send(ser, b'1\r',   0.5, step)   # enable pin 32
            step += 1; send(ser, b'5\r',   0.5, step)   # switch to raw ADC
            step += 1; send(ser, b'x\r',   0.5, step)   # exit Analog Logging

            # ── IMU Logging menu (main menu → 3) ──────────────────────
            #    Accel ±16 g   → option 6 (full-scale submenu) → 4
            #    Gyro OFF      → option 3 (toggle; assumes currently ON)
            #    Mag OFF       → option 4 (toggle; assumes currently ON)
            #    Temp OFF      → option 5 (toggle; assumes currently ON)
            step += 1; send(ser, b'3\r',   0.5, step)
            step += 1; send(ser, b'6\r',   0.5, step)   # open accel full-scale
            step += 1; send(ser, b'4\r',   0.5, step)   # ±16 g
            step += 1; send(ser, b'3\r',   0.5, step)   # disable gyro
            step += 1; send(ser, b'4\r',   0.5, step)   # disable mag
            step += 1; send(ser, b'5\r',   0.5, step)   # disable temp
            step += 1; send(ser, b'x\r',   0.5, step)   # exit IMU Logging

            # ── Exit main menu — saves settings and restarts logging ───
            step += 1; send(ser, b'x\r',   1.0, step)

        print(f"\n  ✅  Fully configured: {port_name}")

    except Exception as exc:
        print(f"\n  ❌  Pass 2 failed on {port_name}: {exc}")


def find_ola_ports() -> list[str]:
    """Auto-detect OLA boards (SparkFun / CH340 / FTDI USB-serial adapters)."""
    ports = serial.tools.list_ports.comports()
    return [
        p.device for p in ports
        if any(kw in (p.description or '') for kw in ("USB", "CH340", "FTDI", "Serial"))
    ]


if __name__ == "__main__":
    t0 = datetime.datetime.now()
    print("\nOpenLog Artemis — Automated Configuration Script")
    print(f"PC clock     : {t0.strftime('%Y/%m/%d  %H:%M:%S')}  EST (UTC-5)")
    print(f"Sample rate  : 100 Hz target  (~90–95 Hz actual — acceptable)")
    print(f"Baud rate    : 240300 → {TARGET_BAUD}  (two-pass reconnect)")
    print(f"Analog pin 32: Enabled  (microphone ENVELOPE), Raw ADC output")
    print(f"IMU          : Accel ±16g  |  Gyro OFF  |  Mag OFF  |  Temp OFF")
    print()
    print("⚠️  TOGGLE WARNING: IMU gyro/mag/temp options are toggles.")
    print("   Script assumes factory defaults (all ON). If already OFF,")
    print("   they will be re-enabled. Verify board state before running.")
    print()

    ola_ports = find_ola_ports()
    if not ola_ports:
        print("No OLA ports found. Check USB connections and try again.")
    else:
        print(f"Found {len(ola_ports)} port(s): {ola_ports}\n")
        for port in ola_ports:
            configure_board(port)

    print("\nAll boards processed.")