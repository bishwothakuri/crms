import paho.mqtt.client as mqtt
import os
from python_on_whales import docker

# MQTT connection details
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_BUILD_PROMETHEUS = "build/prometheus"

class BuilderMQTT:
    def __init__(self):
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def connect(self):
        # Connect to the broker
        self.client.connect(BROKER_HOST, BROKER_PORT, 60)

    def on_connect(self, client, userdata, flags, rc):
        print("Connected to MQTT Broker")
        self.client.subscribe(TOPIC_BUILD_PROMETHEUS)

    def on_message(self, client, userdata, msg):
        # Handle the message received
        config_file = msg.payload.decode()
        print(f"Received build task with config file: {config_file}")
        self.build_and_run_prometheus(config_file)

    def build_and_run_prometheus(self, config_file):
        try:
            # Check if the configuration file exists
            if not os.path.exists(config_file):
                print(f"Configuration file {config_file} not found.")
                return

            # Get the directory of the config file
            config_dir = os.path.dirname(config_file)
            print(f"Changing working directory to {config_dir}")
            os.chdir(config_dir)

            # Build and run Prometheus using docker-compose
            print(f"Building and running Prometheus using {config_file}...")

            # Set COMPOSE_FILE environment variable to point to the correct file
            os.environ['COMPOSE_FILE'] = config_file

            # Use python-on-whales to run docker-compose (without 'file' argument)
            docker.compose.up(detach=True, build=True)

            print("Prometheus is up and running.")

        except Exception as e:
            print(f"Error during Prometheus build and run: {e}")

    def start(self):
        # Start the MQTT loop
        self.client.loop_forever()

if __name__ == "__main__":
    builder = BuilderMQTT()
    builder.connect()
    builder.start()
