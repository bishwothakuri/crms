import paho.mqtt.client as mqtt
import os

# MQTT connection details
BROKER_HOST = "localhost"
BROKER_PORT = 1883
TOPIC_BUILD_PROMETHEUS = "build/prometheus"

class CoordinatorMQTT:
    def __init__(self):
        self.client = mqtt.Client()

    def connect(self):
        # Connect to the MQTT broker
        self.client.connect(BROKER_HOST, BROKER_PORT, 60)

    def send_build_task(self):
        # Correct the path to point to the config directory relative to the project root
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        config_file = os.path.join(project_root, "config", "prometheus-docker-compose.yml")
        print(f"Sending Prometheus build task with config file: {config_file}")

        # Publish the config file path to the build topic
        self.client.publish(TOPIC_BUILD_PROMETHEUS, payload=config_file, qos=1)

    def disconnect(self):
        self.client.disconnect()

if __name__ == "__main__":
    coordinator = CoordinatorMQTT()
    coordinator.connect()

    # Send Prometheus build task
    coordinator.send_build_task()

    # Disconnect cleanly
    coordinator.disconnect()
