# ESP32-CAM QR Code Reader Setup

This guide provides detailed instructions for setting up and using the ESP32-CAM module for QR code reading functionality.

## Hardware Specifications

### ESP32-CAM Module
- Chip: ESP32-D0WDQ6 (revision v1.0)
- Features: 
  - WiFi
  - Bluetooth
  - Dual Core
  - 240MHz CPU
  - VRef calibration in efuse
- Crystal: 40MHz
- Camera: OV2640 camera module
- Flash: 4MB

## Development Environment Setup

### 1. Python Environment Setup

1. Create a virtual environment:
```bash
python -m venv .venv
```

2. Activate the virtual environment:
- Windows:
```bash
.venv\Scripts\activate
```
- Linux/Mac:
```bash
source .venv/bin/activate
```

3. Install required tools:
```bash
pip install mpremote
```

### 2. MicroPython Setup

1. Download the latest MicroPython firmware for ESP32-CAM
2. Flash the firmware to your ESP32-CAM module

## Working with ESP32

### File Management

1. Upload files to ESP32:
```bash
mpremote cp <filename> :
```

2. Run a program:
```bash
mpremote run <filename>
```

3. List files on ESP32:
```bash
mpremote ls
```

4. **Automatic Execution on Boot:**
   - To make a script run automatically when the ESP32 boots up, it **must** be named `main.py` and placed in the root directory of the device's filesystem.
   - MicroPython first runs `boot.py` (if it exists) for initial setup (like WiFi), and then runs `main.py`.

5. Uploading a file as `main.py`:
   - You can upload a local file (e.g., `my_script.py`) and name it `main.py` directly on the ESP32 using this command (replace `COM4` and `my_script.py` as needed):
   ```bash
   mpremote connect COM4 fs cp my_script.py :main.py
   ```

Example workflow with `mpremote`:
```bash
# Connect to ESP32 on COM4 and copy local 'qr_esp32.py' to '/pyboard/main.py'
mpremote connect COM4 fs cp qr_esp32.py :main.py

# List files on the ESP32 to verify 'main.py' is present
mpremote connect COM4 fs ls
# Or connect and list in one command (replace COM4):
# mpremote connect COM4 fs ls
```

### Alternative Commands
If direct `mpremote`

## Remote Reset Functionality

### Visual Reset Indicator
The ESP32-CAM includes a visual indicator for system resets:
- When the device resets (either remotely or manually), the flash LED will:
  - Turn on for 3 seconds
  - Turn off automatically
- This provides a clear visual confirmation that the device has completed its reset cycle

### Remote Reset via MQTT
The device can be reset remotely through MQTT:

1. **Reset Command Format:**
   ```json
   {
     "action": "reset"
   }
   ```

2. **Topic:**
   - Send the reset command to: `vending/machine/{MACHINE_ID}/trigger`
   - Example: `vending/machine/VENDING_001/trigger`

3. **Reset Process:**
   - Device publishes "resetting" status
   - Flash LED indicates reset (3 seconds on)
   - Device reboots automatically
   - After reboot, normal operation resumes

4. **Example MQTT Command:**
   ```bash
   mosquitto_pub -h YOUR_MQTT_SERVER -p 1883 -t "vending/machine/VENDING_001/trigger" -m '{"action": "reset"}'
   ```

**Note:** The flash LED indicator works for all types of resets, not just remote MQTT-triggered ones.