import network
# import urequests # Commented out as not used in MQTT logic
# import esp # Commented out as not used in MQTT logic
import time
import logging
from umqtt.simple import MQTTClient
import machine

# Configure logging
logging.basicConfig(level=logging.INFO)

# WiFi credentials
WIFI_SSID = "your_ssid_here"
WIFI_PASSWORD = "your_password_here"

# --- IMPORTANT: SET THIS FOR EACH DEVICE --- 
DEVICE_QRCODE_ID = "YOUR_UNIQUE_ID_HERE" # Replace with the specific qrcode_id for this ESP32
# ------------------------------------------

# # AWS S3 configuration - Commented out as not used in MQTT logic
# S3_BUCKET_HOST = "YOUR_S3_BUCKET_HOST"
# FIRMWARE_PATH = "YOUR_FIRMWARE_PATH"
# FIRMWARE_URL = f"https://{S3_BUCKET_HOST}/{FIRMWARE_PATH}"

# MQTT Configuration
MQTT_BROKER = "your_mqtt_broker_ip_or_domain"  # Replace with your Lightsail PUBLIC IP or domain
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"vending_{DEVICE_QRCODE_ID}" # Unique client ID based on device ID
MQTT_TOPIC_SUB = f"vending/{DEVICE_QRCODE_ID}/trigger".encode('utf-8') # Topic to subscribe to, derived from device ID
# Define the pin connected to the vending machine trigger (e.g., GPIO 2)
VENDING_PIN = 2

def connect_wifi():
    """Connect to WiFi network"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        logging.info('Connecting to WiFi...')
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)

        # Wait for connection with timeout
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1

        if wlan.isconnected():
            logging.info('WiFi connected successfully')
            logging.info(f'Network config: {wlan.ifconfig()}')
            return True
        else:
            logging.error('Failed to connect to WiFi')
            return False
    else:
        logging.info('Already connected to WiFi')
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

# MQTT Callback function
def sub_cb(topic, msg):
    """Callback function for subscribed MQTT topics"""
    logging.info(f"Received message: Topic='{topic.decode()}', Message='{msg.decode()}'")
    if topic == MQTT_TOPIC_SUB and msg == b'1':
        logging.info("Triggering vending machine...")
        pin = machine.Pin(VENDING_PIN, machine.Pin.OUT)
        pin.on()
        time.sleep(0.1) # Keep pin high for 100ms
        pin.off()
        logging.info("Vending machine triggered.")
    else:
        logging.warning(f"Received unexpected message or topic.")


def main():
    """Main function - Connects to WiFi and handles MQTT messages"""
    logging.info('Starting ESP32 Vending MQTT Client')

    # Connect to WiFi
    if not connect_wifi():
        logging.error('Failed to connect to WiFi. Cannot proceed.')
        # Optional: Implement retry logic or deep sleep here
        return

    # Initialize MQTT Client
    # Ensure MQTT_CLIENT_ID is unique if running multiple instances
    logging.info(f"Initializing MQTT Client with ID: {MQTT_CLIENT_ID}")
    client = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
    client.set_callback(sub_cb)

    while True: # Main loop
        try:
            if not client.is_conn_issue():
                 # If not connected, try to connect.
                logging.info(f"Attempting to connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
                client.connect()
                logging.info(f"Connected to MQTT broker. Subscribing to topic '{MQTT_TOPIC_SUB.decode()}'...")
                client.subscribe(MQTT_TOPIC_SUB)
                logging.info("Waiting for coupons...")
            else:
                # Check for new messages
                client.check_msg()
                # Send periodic pings or other actions if needed
                # client.ping() # Example: Send keep-alive ping
                time.sleep(1) # Check for messages every second

        except OSError as e:
            logging.error(f"MQTT Connection Error: {e}. Reconnecting...")
            # Optional: Add a small delay before attempting to reconnect
            time.sleep(5)
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            time.sleep(10) # Longer delay for unknown errors

if __name__ == '__main__':
    main()