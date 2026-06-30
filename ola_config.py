import serial
import serial.tools.list_ports
import time
import datetime


UTC_OFFSET = "-5"
STARTBAUD = 115200
NEWBAUD   = 230400
KNOWN_VIDS = {0x1A86, 0x0403, 0x10C4}
RTC_NAV_DELAY = 5.0


def send(ser, payload, delay, step):
    ser.write(payload)
    time.sleep(delay)
    resp = ser.read_all().decode(errors='ignore').strip()
    label = payload.decode(errors='ignore').strip() or "<CR>"
    print(f"  [{step:02d}] ← {label!r:12s}  »  {resp[:200] if resp else '(no response)'}")
    return resp


def get_timestamp(extra=0.0):
    t = datetime.datetime.now() + datetime.timedelta(seconds=extra)
    return {
        "year_2d": f"{t.year % 100:02d}",
        "month":   f"{t.month:02d}",
        "day":     f"{t.day:02d}",
        "hour":    f"{t.hour:02d}",
        "minute":  f"{t.minute:02d}",
        "second":  f"{t.second:02d}",
    }


def open_port(port, baud):
    fallback = NEWBAUD if baud == STARTBAUD else STARTBAUD
    for rate in (baud, fallback):
        try:
            ser = serial.Serial(port, rate, timeout=2)
            print(f"    Connected at {rate} baud.")
            return ser
        except Exception as e:
            print(f"    Could not connect at {rate}: {e}")
    return None


def configure_board(port):
    print("\n" + "═"*60)
    print(f"  Configuring: {port}")
    print("═"*60)

    step = 0

    # PASS 1 — Change baud rate
    ser = open_port(port, STARTBAUD)
    if ser is None:
        print(f"  Skipping {port}: cannot open.")
        return

    with ser:
        time.sleep(1.5)
        step += 1; send(ser, b"\r", 1.0, step)
        step += 1; send(ser, b"1\r", 0.5, step)
        step += 1; send(ser, b"3\r", 0.5, step)
        step += 1; send(ser, f"{NEWBAUD}\r".encode(), 1.5, step)

    print(f"\n    Baud changed to {NEWBAUD}. Reconnecting...")
    time.sleep(2)

    # PASS 2 — Full config at NEWBAUD
    ser = open_port(port, NEWBAUD)
    if ser is None:
        print(f"  Skipping {port}: cannot reconnect at {NEWBAUD}.")
        return

    with ser:
        # DTR reset
        try:
            ser.dtr = False; time.sleep(0.1)
            ser.dtr = True;  time.sleep(2.5)
            print("    DTR reset pulse sent.")
        except:
            print("    DTR reset not supported.")

        step += 1; send(ser, b"\r", 1.0, step)

        # Time Stamp menu
        ts = get_timestamp(RTC_NAV_DELAY)
        step += 1; send(ser, b"2\r", 0.5, step)

        # Date
        step += 1; send(ser, b"4\r", 0.5, step)
        step += 1; send(ser, f"{ts['year_2d']}\r".encode(), 0.4, step)
        step += 1; send(ser, f"{ts['month']}\r".encode(),   0.4, step)
        step += 1; send(ser, f"{ts['day']}\r".encode(),     0.5, step)

        # Time
        step += 1; send(ser, b"6\r", 0.5, step)
        step += 1; send(ser, f"{ts['hour']}\r".encode(),   0.4, step)
        step += 1; send(ser, f"{ts['minute']}\r".encode(), 0.4, step)
        step += 1; send(ser, f"{ts['second']}\r".encode(), 0.5, step)

        # UTC offset
        step += 1; send(ser, b"9\r", 0.5, step)
        step += 1; send(ser, f"{UTC_OFFSET}\r".encode(), 0.5, step)

        # Exit Time Stamp (3 exits to be safe)
        step += 1; send(ser, b"x\r", 0.5, step)
        step += 1; send(ser, b"x\r", 0.5, step)
        step += 1; send(ser, b"x\r", 0.5, step)

        # Sync to main menu
        step += 1; send(ser, b"\r", 0.5, step)

        # Terminal Output → Log Rate
        step += 1; send(ser, b"1\r", 0.5, step)
        step += 1; send(ser, b"4\r", 0.5, step)
        step += 1; send(ser, b"100\r", 0.5, step)
        step += 1; send(ser, b"x\r", 0.5, step)

        step += 1; send(ser, b"\r", 0.5, step)

        # Analog Logging — state-aware, RAW ADC
        resp = send(ser, b"5\r", 0.5, step)
        pin11_enabled = "Log analog pin 11 (2V Max): Enabled" in resp

        if not pin11_enabled:
            step += 1; send(ser, b"1\r", 0.5, step)

        step += 1; send(ser, b"5\r", 0.5, step)  # RAW ADC
        step += 1; send(ser, b"x\r", 0.5, step)

        step += 1; send(ser, b"\r", 0.5, step)

        # IMU Logging — state-aware
        resp = send(ser, b"3\r", 0.5, step)

        gyro_on = "Gyro Logging: Enabled" in resp
        mag_on  = "Magnetometer Logging: Enabled" in resp
        temp_on = "Temperature Logging: Enabled" in resp

        step += 1; send(ser, b"6\r", 0.5, step)
        step += 1; send(ser, b"3\r", 0.5, step)  # ±16 g

        if gyro_on:
            step += 1; send(ser, b"3\r", 0.5, step)
        if mag_on:
            step += 1; send(ser, b"4\r", 0.5, step)
        if temp_on:
            step += 1; send(ser, b"5\r", 0.5, step)

        step += 1; send(ser, b"x\r", 0.5, step)
        step += 1; send(ser, b"x\r", 1.0, step)

    print(f"\n  Fully configured: {port}")


def find_ola_ports():
    ports = serial.tools.list_ports.comports()
    out = []
    for p in ports:
        if p.vid in KNOWN_VIDS:
            out.append(p.device)
        elif p.vid is None and any(k in (p.description or "") for k in ("CH340", "FTDI", "CP210")):
            out.append(p.device)
    return out


if __name__ == "__main__":
    print("\nOpenLog Artemis — Automated Configuration Script")
    print(f"Baud rate: {STARTBAUD} → {NEWBAUD}")
    print("Analog pin 11: RAW ADC")
    print("IMU: Accel ±16g, Gyro/Mag/Temp OFF\n")

    ports = find_ola_ports()
    if not ports:
        print("No OLA ports found.")
    else:
        print(f"Found {len(ports)} port(s): {ports}\n")
        for p in ports:
            configure_board(p)

    print("\nAll boards processed.")
