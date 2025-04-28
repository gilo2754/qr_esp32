"""
ESP32 Vending Machine MQTT Controller (Template)

Connects ESP32 to WiFi and MQTT broker. Listens for commands on a machine-specific
topic to trigger flash LED pulses or perform a remote reset. Publishes confirmation,
optional status, and periodic health messages back. Indicates reset via flash LED on boot.

Requires configuration of: WIFI_SSID, WIFI_PASSWORD, MACHINE_ID, MQTT_BROKER.

MQTT Topics (replace {MACHINE_ID}):

1. SUB: `vending/machine/{MACHINE_ID}/trigger` (Commands to ESP32)
   - Payload: JSON
   - Pulse Cmd: `{"qrcode_id": "...", "pulses": N}` (Blinks LED N times)
   - Reset Cmd: `{"action": "reset"}` (Reboots ESP32)

2. PUB: `vending/machine/{MACHINE_ID}/confirm` (Action Confirmation)
   - Payload: JSON `{"qrcode_id": "...", "status": "success"|"failure"}`

3. PUB: `vending/machine/{MACHINE_ID}/status` (Optional Status)
   - Payload: JSON with action details or `{"status": "resetting"}`

4. PUB: `vending/machine/{MACHINE_ID}/health` (Periodic Health Check)
   - Payload: JSON `{"status": "healthy", "uptime_s": N, "mem_free_b": N, "mem_alloc_b": N}`
   - Published every HEALTH_CHECK_INTERVAL seconds.
"""

import network
# import urequests # Commented out as not used in MQTT logic
# import esp # Commented out as not used in MQTT logic
import time
# import logging # Removed logging module
from umqtt.simple import MQTTClient
import machine
import ujson # Import ujson for creating JSON payloads
import gc # Import garbage collector for memory check

# Configure logging - Removed
# logging.basicConfig(level=logging.INFO)

# WiFi credentials
WIFI_SSID = "ssid"
WIFI_PASSWORD = "password"

# --- IMPORTANT: SET THIS FOR EACH DEVICE --- 
# DEVICE_QRCODE_ID = "YOUR_UNIQUE_ID_HERE" # Replace with the specific qrcode_id for this ESP32 - NO LONGER USED for topic
MACHINE_ID = "VENDING_001" # Replace with the specific Machine ID for this ESP32
# ------------------------------------------

# # AWS S3 configuration - Commented out as not used in MQTT logic
# S3_BUCKET_HOST = "YOUR_S3_BUCKET_HOST"
# FIRMWARE_PATH = "YOUR_FIRMWARE_PATH"
# FIRMWARE_URL = f"https://{S3_BUCKET_HOST}/{FIRMWARE_PATH}"

# MQTT Configuration
MQTT_BROKER = "x.x.x.x"  # Replace with your Lightsail PUBLIC IP or domain
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"vending_{MACHINE_ID}" # Unique client ID based on machine ID
MQTT_TOPIC_SUB = f"vending/machine/{MACHINE_ID}/trigger".encode('utf-8') # Topic to subscribe to, derived from machine ID
MQTT_TOPIC_PUB = f"vending/machine/{MACHINE_ID}/status".encode('utf-8')  # Topic to publish status back
MQTT_TOPIC_CONFIRM = f"vending/machine/{MACHINE_ID}/confirm".encode('utf-8') # NEW: Topic for publishing redeem confirmations
MQTT_TOPIC_HEALTH = f"vending/machine/{MACHINE_ID}/health".encode('utf-8') # Topic for health status

# Health Check Configuration
HEALTH_CHECK_INTERVAL = 60  # Interval in seconds (e.g., 60 for 1 minute)
last_health_check = 0

# --- Pin Configuration --- 
# Define the pin connected to the vending machine trigger (e.g., relay)
VENDING_PIN = 2 # Keep previous pin if needed, or remove if only using flash
# Define the pin connected to the Camera Flash LED (Commonly GPIO 4 on ESP32-CAM boards)
FLASH_PIN = 4 
# ------------------------

def connect_wifi():
    """Connect to WiFi network"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        # logging.info('Connecting to WiFi...')
        print("INFO: Connecting to WiFi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

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

# # update_firmware function commented out as not used in MQTT logic
# def update_firmware():
#     """Download and install firmware update from S3"""
#     try:
#         logging.info('Starting firmware update...')
#         # ... (rest of the function)
#     except Exception as e:
#         logging.error(f'Error during update: {str(e)}')
#         return False

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

# MQTT Callback function
def sub_cb(topic, msg):
    """Callback function for subscribed MQTT topics"""
    global client # Declare client as global to use it for publishing
    payload_str = msg.decode()
    print(f"INFO: Received raw message: Topic='{topic.decode()}', Payload='{payload_str}'")

    if topic == MQTT_TOPIC_SUB:
        try:
            payload_data = ujson.loads(payload_str)

            # Check for reset command
            if payload_data.get("action") == "reset":
                print("INFO: Received reset command. Resetting device...")
                try:
                    client.publish(MQTT_TOPIC_PUB, ujson.dumps({"status": "resetting"}).encode('utf-8'))
                    print("INFO: Published 'resetting' status.")
                    time.sleep(1) # Give time for the message to be sent
                except Exception as pub_err:
                    print(f"ERROR: Could not publish resetting status: {pub_err}")
                
                machine.reset() # Execute hardware reset
                return # Code won't continue after this

            # Existing pulse logic
            num_pulses = int(payload_data.get('pulses', 0))
            qrcode_id = payload_data.get('qrcode_id')
            action_status = "failure" # Default to failure
            error_detail = ""

            if qrcode_id is None:
                raise ValueError("Missing 'qrcode_id' in payload")

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
                        # Optional: Check for MQTT messages during long sequences
                        # client.check_msg() 
                    
                    print(f"INFO: Pulse sequence for QR ID {qrcode_id} completed successfully.")
                    action_status = "success" # Action succeeded
                except Exception as pulse_err:
                    # If pulsing fails mid-way, it's still a failure for confirmation
                    action_status = "failure"
                    error_detail = f"Error during pulse generation for QR ID {qrcode_id}: {pulse_err}"
                    print(f"ERROR: {error_detail}")
                # -----------------------------------
                
            else:
                 print(f"INFO: Received {num_pulses} pulses for QR ID {qrcode_id}. No action needed.")
                 action_status = "success" # Consider 0 pulses a success (nothing to do)
                 error_detail = "No pulses requested"

        except ValueError as ve:
            action_status = "failure"
            error_detail = f"Could not parse payload or missing field: {ve}"
            print(f"ERROR: {error_detail} - Payload: {payload_str}")
        except Exception as e:
            action_status = "failure"
            error_detail = f"General error processing message: {e}"
            print(f"ERROR: {error_detail} - Payload: {payload_str}")
        
        # --- Publish Confirmation Status --- 
        if qrcode_id:
            try:
                confirm_payload = {
                    "qrcode_id": qrcode_id,
                    "status": action_status # 'success' or 'failure'
                }
                confirm_json = ujson.dumps(confirm_payload)
                client.publish(MQTT_TOPIC_CONFIRM, confirm_json.encode('utf-8'))
                print(f"INFO: Published confirmation to {MQTT_TOPIC_CONFIRM.decode()}: {confirm_json}")
            except Exception as pub_err:
                # This is problematic - if confirmation fails, the backend won't know
                print(f"CRITICAL ERROR: Failed to publish confirmation for QR ID {qrcode_id} to MQTT: {pub_err}")
        else:
             print("WARNING: Cannot send confirmation - qrcode_id was not extracted from payload.")
        # ------------------------------------
        
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
    global client # Make client global so sub_cb can access it
    """Main function - Connects to WiFi and handles MQTT messages"""
    # logging.info(f'Starting ESP32 Vending MQTT Client for Machine ID: {MACHINE_ID}')
    print(f'INFO: Starting ESP32 Vending MQTT Client for Machine ID: {MACHINE_ID}')

    # Initialize last health check time at start
    global last_health_check
    last_health_check = time.time() 

    # Indicate reset with flash LED
    indicate_reset()

    # Connect to WiFi
    if not connect_wifi():
        # logging.error('Failed to connect to WiFi. Cannot proceed.')
        print('ERROR: Failed to connect to WiFi. Cannot proceed.')
        # Optional: Implement retry logic or deep sleep here
        return

    # Initialize MQTT Client
    # Ensure MQTT_CLIENT_ID is unique if running multiple instances
    print(f"INFO: Initializing MQTT Client with ID: {MQTT_CLIENT_ID}")
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