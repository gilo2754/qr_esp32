"""
ESP32 Vending Machine MQTT Controller (Template)

Connects ESP32 to WiFi and MQTT broker. Listens for commands on a machine-specific
topic to trigger flash LED pulses, perform a remote reset, or initiate an Over-the-Air
(OTA) update of the main script. Publishes confirmation, optional status, and periodic
health messages back. Indicates reset via flash LED on boot.

Requires configuration of: WIFI_SSID, WIFI_PASSWORD, MACHINE_ID, MQTT_BROKER.

MQTT Topics (replace {MACHINE_ID}):

1. SUB: `vending/machine/{MACHINE_ID}/trigger` (Commands to ESP32)
   - Payload: JSON
   - Pulse Cmd: `{"qrcode_id": "...", "pulses": N}` (Blinks LED N times)
   - Reset Cmd: `{"action": "reset"}` (Reboots ESP32)
   - OTA Update Cmd: `{"action": "update", "url": "http://.../new_main.py"}` (Downloads & replaces main.py, then reboots)

2. PUB: `vending/machine/{MACHINE_ID}/confirm` (Action Confirmation for Pulses)
   - Payload: JSON `{"qrcode_id": "...", "status": "success"|"failure"}`

3. PUB: `vending/machine/{MACHINE_ID}/status` (Optional Status / OTA Status)
   - Payload: JSON with action details, `{"status": "resetting"}`, or OTA status like 
     `{"status": "ota_starting"|"ota_success_rebooting"|"ota_download_failed"|...}`

4. PUB: `vending/machine/{MACHINE_ID}/health` (Periodic Health Check)
   - Payload: JSON `{"status": "healthy", "uptime_s": N, "mem_free_b": N, "mem_alloc_b": N}`
   - Published every HEALTH_CHECK_INTERVAL seconds.
"""

import network
import urequests # Un-comment or add for OTA updates
# import esp # Commented out as not used in MQTT logic
import time
# import logging # Removed logging module
from umqtt.simple import MQTTClient
import machine
import ujson # Import ujson for creating JSON payloads
import gc # Import garbage collector for memory check
import uos # Import for file operations (OTA update)

# logging.basicConfig(level=logging.INFO)

# Default configuration (optional, provides fallback if config loading fails)
# config = {
#     "wifi_ssid": "DEFAULT_SSID",
#     "wifi_password": "DEFAULT_PASSWORD",
#     "machine_id": "DEFAULT_MACHINE_ID",
#     "mqtt_broker": "127.0.0.1"
# }

CONFIG_FILE = 'config.json'

def load_config():
    """Loads configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config_data = ujson.load(f)
            print(f"INFO: Configuration loaded successfully from {CONFIG_FILE}")
            # Basic validation (check if keys exist)
            required_keys = ["wifi_ssid", "wifi_password", "machine_id", "mqtt_broker"]
            for key in required_keys:
                if key not in config_data:
                    raise ValueError(f"Missing key in config: {key}")
            return config_data
    except OSError:
        print(f"ERROR: Configuration file {CONFIG_FILE} not found!")
        return None
    except ValueError as e:
        print(f"ERROR: Invalid JSON or missing key in {CONFIG_FILE}: {e}")
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error loading configuration: {e}")
        return None

# --- IMPORTANT: SET THIS FOR EACH DEVICE --- 
# DEVICE_QRCODE_ID = "YOUR_UNIQUE_ID_HERE" # Replace with the specific qrcode_id for this ESP32 - NO LONGER USED for topic
# MACHINE_ID = "VENDING_001" # Replace with the specific Machine ID for this ESP32
# ------------------------------------------

# MQTT Configuration (derived from loaded config or defaults)
MQTT_PORT = 1883
# MQTT topics will be constructed after config is loaded inside main()

# Health Check Configuration
HEALTH_CHECK_INTERVAL = 60  # Interval in seconds (e.g., 60 for 1 minute)
last_health_check = 0

# --- Pin Configuration --- 
# Define the pin connected to the vending machine trigger (e.g., relay)
VENDING_PIN = 2 # Keep previous pin if needed, or remove if only using flash
# Define the pin connected to the Camera Flash LED (Commonly GPIO 4 on ESP32-CAM boards)
FLASH_PIN = 4 
# ------------------------

def connect_wifi(config):
    """Connect to WiFi network using loaded config"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        # logging.info('Connecting to WiFi...')
        print("INFO: Connecting to WiFi...")
        wlan.connect(config['wifi_ssid'], config['wifi_password'])

        # Wait for connection with timeout
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1

        if wlan.isconnected():
            # logging.info('WiFi connected successfully')
            # logging.info(f'Network config: {wlan.ifconfig()}')
            print("INFO: WiFi connected successfully")
            print(f"INFO: Network config: {wlan.ifconfig()}")
            return True
        else:
            # logging.error('Failed to connect to WiFi')
            print("ERROR: Failed to connect to WiFi")
            return False
    else:
        # logging.info('Already connected to WiFi')
        print("INFO: Already connected to WiFi")
        return True

# Memory Check function
def check_memory():
    """Collect garbage and return free and allocated memory in bytes."""
    gc.collect()
    free_mem = gc.mem_free()
    alloc_mem = gc.mem_alloc()
    print(f"DEBUG: Memory - Free: {free_mem}, Allocated: {alloc_mem}")
    return free_mem, alloc_mem

# Health Check Publisher
def publish_health_status(client):
    """Publish health status to the MQTT health topic."""
    global last_health_check
    current_time = time.time()

    if (current_time - last_health_check) >= HEALTH_CHECK_INTERVAL:
        health_payload = None
        health_json = None
        try:
            # Gather data first
            free_mem, alloc_mem = check_memory()
            uptime = time.time() # Simple uptime (seconds since boot/epoch)

            health_payload = {
                "status": "healthy",
                "uptime_s": int(uptime), # Use int to avoid float issues
                "mem_free_b": free_mem,
                "mem_alloc_b": alloc_mem
            }
            health_json = ujson.dumps(health_payload)
            print(f"DEBUG: Prepared health JSON: {health_json}")

        except Exception as e:
            print(f"ERROR: Failed to prepare health status data: {e}")
            # Don't update last_health_check if data prep fails
            return # Exit if we couldn't even prepare the data

        # Now, attempt to publish the prepared data
        if health_json:
            try:
                print(f"DEBUG: Attempting to publish to {MQTT_TOPIC_HEALTH.decode()}...")
                client.publish(MQTT_TOPIC_HEALTH, health_json.encode('utf-8'))
                print(f"INFO: Successfully published health status: {health_json}")
                # Update last check time ONLY after successful publish
                last_health_check = current_time
            except OSError as pub_e:
                print(f"ERROR: OSError during MQTT publish for health status: {pub_e}. Client might be disconnected.")
                # Don't update last_health_check if publish fails
            except Exception as pub_e:
                print(f"ERROR: Unexpected error during MQTT publish for health status: {pub_e}")
                # Don't update last_health_check if publish fails
        else:
            print("ERROR: Health JSON was not prepared, cannot publish.")

# OTA Update function
def perform_ota_update(url):
    """Downloads a new script from URL, replaces main.py, and resets.
    
    Args:
        url (str): The URL from which to download the new main.py script.
    """
    global client
    temp_script_path = 'main_next.py'
    old_script_path = 'main_old.py'
    current_script_path = 'main.py'
    
    print(f"INFO: Starting OTA update from URL: {url}")
    
    # Publish status: starting update
    try:
        client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "ota_starting", "url": url}).encode('utf-8'))
    except Exception as pub_err:
        print(f"WARNING: Could not publish ota_starting status: {pub_err}")

    download_successful = False
    try:
        # Download the new script
        print(f"DEBUG: Downloading script to {temp_script_path}...")
        response = urequests.get(url)
        
        if response.status_code == 200:
            print(f"DEBUG: Download successful (status code 200). Saving...")
            with open(temp_script_path, 'wb') as f:
                f.write(response.content)
            print(f"INFO: New script saved to {temp_script_path}")
            response.close() # Close the response to free memory
            # Basic validation: Check if file exists and has size > 0
            if uos.stat(temp_script_path)[6] > 0:
                 download_successful = True
                 print("INFO: Basic validation passed (file exists and size > 0).")
            else:
                 print("ERROR: Downloaded file is empty!")
                 uos.remove(temp_script_path) # Clean up empty file
        else:
            print(f"ERROR: Failed to download script. Status code: {response.status_code}")
            response.close()

    except Exception as e:
        print(f"ERROR: Exception during OTA download: {e}")
        # Clean up temporary file if it exists
        try:
            uos.remove(temp_script_path)
        except OSError:
            pass # File might not exist

    # If download was successful, proceed with replacing the script
    if download_successful:
        try:
            # Attempt to remove very old backup, ignore if it doesn't exist
            try:
                uos.remove(old_script_path)
                print(f"DEBUG: Removed old backup {old_script_path}")
            except OSError:
                pass # No old backup existed

            # Rename current main.py to main_old.py
            try:
                uos.rename(current_script_path, old_script_path)
                print(f"DEBUG: Renamed {current_script_path} to {old_script_path}")
            except OSError:
                print(f"WARNING: Could not rename {current_script_path} (might not exist?)")
                # Continue anyway, maybe it's the first deploy

            # Rename the new script to main.py
            uos.rename(temp_script_path, current_script_path)
            print(f"INFO: Renamed {temp_script_path} to {current_script_path}. Update successful.")

            # Publish status: update successful, resetting
            try:
                client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "ota_success_rebooting"}).encode('utf-8'))
            except Exception as pub_err:
                 print(f"WARNING: Could not publish ota_success status: {pub_err}")
            
            # Reset the device to apply the update
            print("INFO: Resetting device to apply update...")
            time.sleep(2) # Short delay to allow MQTT message to send
            machine.reset()

        except Exception as e:
            print(f"ERROR: Exception during file renaming/finalizing OTA: {e}")
            # Publish status: update failed during finalization
            try:
                client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "ota_finalize_failed", "error": str(e)}).encode('utf-8'))
            except Exception as pub_err:
                 print(f"WARNING: Could not publish ota_finalize_failed status: {pub_err}")
    else:
        print("ERROR: OTA update failed due to download error.")
        # Publish status: update failed during download
        try:
            client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "ota_download_failed"}).encode('utf-8'))
        except Exception as pub_err:
            print(f"WARNING: Could not publish ota_download_failed status: {pub_err}")

# MQTT Callback function
def sub_cb(topic, msg):
    """Callback function for subscribed MQTT topics"""
    global client # Declare client as global to use it for publishing
    payload_str = msg.decode()
    print(f"INFO: Received raw message: Topic='{topic.decode()}', Payload='{payload_str}'")

    if topic == MQTT_TOPIC_SUB:
        try:
            payload_data = ujson.loads(payload_str)
            action = payload_data.get("action")

            # Check for reset command
            if action == "reset":
                print("INFO: Received reset command. Resetting device...")
                try:
                    client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "resetting"}).encode('utf-8'))
                    print("INFO: Published 'resetting' status.")
                    time.sleep(1) # Give time for the message to be sent
                except Exception as pub_err:
                    print(f"ERROR: Could not publish resetting status: {pub_err}")
                
                machine.reset() # Execute hardware reset
                return # Code won't continue after this
            
            # Check for OTA update command
            elif action == "update":
                ota_url = payload_data.get("url")
                if ota_url:
                    print(f"INFO: Received OTA update command for URL: {ota_url}")
                    perform_ota_update(ota_url)
                    # perform_ota_update handles reset, so we should not reach here if successful
                    print("ERROR: OTA function returned unexpectedly (update likely failed before reset). Waiting for next command.")
                    return
                else:
                    print("ERROR: Received 'update' action but missing 'url' in payload.")
                    # Optionally publish an error status back
                    try:
                        client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "ota_error", "error": "missing_url"}).encode('utf-8'))
                    except Exception as pub_err:
                         print(f"WARNING: Could not publish ota_error status: {pub_err}")
                    return

            # Existing pulse logic (if action is not reset or update)
            else:
                num_pulses = int(payload_data.get('pulses', 0))
                qrcode_id = payload_data.get('qrcode_id')
                action_status = "failure" # Default to failure
                error_detail = ""

                if qrcode_id is None:
                    raise ValueError("Missing 'qrcode_id' in payload for pulse action")

                if num_pulses > 0:
                    print(f"INFO: Received instruction for {num_pulses} pulse(s) for QR ID {qrcode_id}. Triggering...")
                    # Initialize flash pin
                    flash = machine.Pin(FLASH_PIN, machine.Pin.OUT)
                    
                    # --- Attempt to Generate Pulses --- 
                    try:
                        for i in range(num_pulses):
                            flash.on()  # Turn flash on
                            time.sleep(0.2) # On duration
                            flash.off() # Turn flash off
                            time.sleep(0.3) # Off duration (pause between blinks)
                        print(f"INFO: Pulse sequence for QR ID {qrcode_id} completed successfully.")
                        action_status = "success" # Action succeeded
                    except Exception as pulse_err:
                        action_status = "failure"
                        error_detail = f"Error during pulse generation for QR ID {qrcode_id}: {pulse_err}"
                        print(f"ERROR: {error_detail}")
                    # -----------------------------------
                    
                else:
                    print(f"INFO: Received {num_pulses} pulses for QR ID {qrcode_id}. No action needed.")
                    action_status = "success" # Consider 0 pulses a success (nothing to do)
                    error_detail = "No pulses requested"

                # --- Publish Confirmation Status for pulse action --- 
                if qrcode_id: # qrcode_id should exist if we reached here
                    try:
                        confirm_payload = {
                            "qrcode_id": qrcode_id,
                            "status": action_status # 'success' or 'failure'
                        }
                        confirm_json = ujson.dumps(confirm_payload)
                        client.publish(MQTT_TOPIC_CONFIRM, confirm_json.encode('utf-8'))
                        print(f"INFO: Published confirmation to {MQTT_TOPIC_CONFIRM.decode()}: {confirm_json}")
                    except Exception as pub_err:
                        print(f"CRITICAL ERROR: Failed to publish confirmation for QR ID {qrcode_id} to MQTT: {pub_err}")
                
                # --- (Optional) Publish General Device Status (can be kept or removed) ---
                # This provides more detailed status but isn't strictly needed for the redeem logic
                try:
                    # Keep track of pulses attempted vs generated if needed
                    pulses_generated = num_pulses if action_status == "success" else 0
                    device_status_payload = {
                        "last_action_status": action_status,
                        "last_qrcode_id": qrcode_id,
                        "pulses_requested": num_pulses if qrcode_id else None,
                        "pulses_generated": pulses_generated,
                        "error": error_detail if action_status == "failure" else ""
                    }
                    device_status_json = ujson.dumps(device_status_payload)
                    client.publish(MQTT_TOPIC_PUB, device_status_json.encode('utf-8'))
                    print(f"INFO: Published device status to {MQTT_TOPIC_PUB.decode()}: {device_status_json}")
                except Exception as pub_err:
                    print(f"ERROR: Failed to publish device status to MQTT: {pub_err}")
                # ----------------------------------------------------------------------

        except ValueError as ve:
            # Handle JSON parsing errors or missing fields for pulse action
            print(f"ERROR: Could not parse payload or missing required field: {ve} - Payload: {payload_str}")
            # Optionally publish an error status back
            try:
                client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "payload_error", "error": str(ve)}).encode('utf-8'))
            except Exception as pub_err:
                 print(f"WARNING: Could not publish payload_error status: {pub_err}")

        except Exception as e:
            # General catch-all for other errors during message processing
            print(f"ERROR: General error processing message: {e} - Payload: {payload_str}")
            try:
                client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "processing_error", "error": str(e)}).encode('utf-8'))
            except Exception as pub_err:
                 print(f"WARNING: Could not publish processing_error status: {pub_err}")

    else:
        print(f"WARNING: Received message on unexpected topic: {topic.decode()}")

def indicate_reset():
    """Function to indicate a reset by flashing the LED for 3 seconds"""
    try:
        flash = machine.Pin(FLASH_PIN, machine.Pin.OUT)
        print("INFO: Indicating reset with flash LED...")
        flash.on()  # Turn flash on
        time.sleep(3)  # Keep it on for 3 seconds
        flash.off()  # Turn flash off
        print("INFO: Reset indication complete")
    except Exception as e:
        print(f"ERROR: Could not indicate reset with flash: {e}")

def main():
    global client, last_health_check
    global MQTT_CLIENT_ID, MQTT_TOPIC_SUB, MQTT_TOPIC_PUB, MQTT_TOPIC_CONFIRM, MQTT_TOPIC_HEALTH # Declare topics as global

    # --- Load Configuration --- 
    config = load_config()
    if config is None:
        print("FATAL: Could not load configuration. Halting.")
        # Optional: Blink LED rapidly to indicate fatal error
        time.sleep(10)
        machine.reset() # Resetting might allow manual intervention
        return # Stop execution
    # --------------------------

    # --- Construct MQTT topics and Client ID using loaded config --- 
    MACHINE_ID = config['machine_id'] # Get Machine ID from config
    MQTT_BROKER = config['mqtt_broker'] # Get Broker from config
    MQTT_CLIENT_ID = f"vending_{MACHINE_ID}"
    MQTT_TOPIC_SUB = f"vending/machine/{MACHINE_ID}/trigger".encode('utf-8')
    MQTT_TOPIC_PUB = f"vending/machine/{MACHINE_ID}/status".encode('utf-8')
    MQTT_TOPIC_CONFIRM = f"vending/machine/{MACHINE_ID}/confirm".encode('utf-8')
    MQTT_TOPIC_HEALTH = f"vending/machine/{MACHINE_ID}/health".encode('utf-8')
    # -------------------------------------------------------------

    print(f'INFO: Starting *** UPDATED-OTA-REMOTE *** ESP32 Vending MQTT Client for Machine ID: {MACHINE_ID}')
    
    last_health_check = time.time()
    indicate_reset()

    # Pass config to connect_wifi
    if not connect_wifi(config):
        print('ERROR: Failed to connect to WiFi. Cannot proceed.')
        return

    print(f"INFO: Initializing MQTT Client with ID: {MQTT_CLIENT_ID}")
    # Use loaded MQTT_BROKER
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
    client.set_callback(sub_cb)

    # Attempt initial connection
    try:
        print(f"INFO: Attempting initial connection to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect()
        print(f"INFO: Connected to MQTT broker. Subscribing to topic '{MQTT_TOPIC_SUB.decode()}'...")
        client.subscribe(MQTT_TOPIC_SUB)
        print("INFO: Waiting for messages...")
    except OSError as e:
        print(f"ERROR: Initial MQTT connection failed: {e}. Device will likely restart or hang.")
        time.sleep(10)
        machine.reset() # Or handle differently
        return 
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during initial connection: {e}")
        time.sleep(10)
        machine.reset()
        return

    # Main loop
    while True:
        try:
            # Check for new messages and maintain connection
            # check_msg() returns None for no message, or the message topic for PINGREQ/DISCONNECT? (Check docs)
            # It raises OSError on connection issues.
            client.check_msg() 
            
            # Publish health status periodically
            publish_health_status(client)
            
            # Optional: Add a small delay if check_msg is non-blocking and you don't want to hammer CPU
            time.sleep(0.1) 

        except OSError as e:
            print(f"ERROR: MQTT Connection Error/Disconnected: {e}. Reconnecting...")
            # Wait before attempting to reconnect
            time.sleep(5)
            try:
                client.connect() # Attempt to reconnect
                client.subscribe(MQTT_TOPIC_SUB) # Re-subscribe after reconnecting
                print("INFO: Reconnected to MQTT broker and re-subscribed.")
            except Exception as e_conn:
                 print(f"ERROR: An unexpected error occurred during reconnection: {e_conn}")
                 time.sleep(10)
        except Exception as e:
            print(f"ERROR: An unexpected error occurred in main loop: {e}")
            time.sleep(10) # Wait before continuing after unknown error
            machine.reset() # Consider if reset is always best

if __name__ == '__main__':
    main()