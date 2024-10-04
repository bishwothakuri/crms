import os
import json
import datetime
import time
import paho.mqtt.client as mqtt
import yaml
import logging
import threading
import queue
from python_on_whales import docker, DockerException, DockerClient

# Import the common logging configuration
from worker_node.common import logging_config as log_config

logger = logging.getLogger("Builderd")

BROKER = "localhost"
COORDINATOR_TOPIC = "builder/coordinator"
MONITORING_STACK = ["prometheus", "cadvisor", "node-exporter"]  # Services to monitor

# Queue to hold the tasks
task_queue = queue.Queue()


# MQTT Callback for connection
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Successfully connected to MQTT Broker")
    else:
        logger.error(f"Failed to connect to MQTT Broker, return code {rc}")
    client.subscribe("build/task")
    logger.info("Subscribed to topic: build/task")


# MQTT Callback for receiving messages
def on_message(client, userdata, msg):
    yaml_filename = msg.payload.decode()
    logger.info(f"Received build task: Config file = {yaml_filename}")
    # Put the task in the queue for the Task Execution Thread
    task_queue.put(yaml_filename)


# Function to check if monitoring services are up
def is_monitoring_stack_up():
    for service in MONITORING_STACK:
        try:
            status = docker.container.inspect(service).state.running
            if not status:
                logger.info(f"Service {service} is not running yet.")
                return False
        except DockerException as e:
            logger.error(f"Error checking service {service}: {e}")
            return False
    return True


# Send a system ready message to the coordinator
def send_system_ready():
    client = mqtt.Client()
    client.connect(BROKER)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat() + "z"
    message = {
        "sender": "builderd",
        "type": "status",
        "content": "Monitoring stack is up. System is ready.",
        "timestamp": timestamp,
    }
    logger.info(f"Sending system ready message to coordinator: {message}")
    client.publish(COORDINATOR_TOPIC, json.dumps(message), qos=1)
    client.disconnect()


# Thread responsible for listening for MQTT messages
class TaskListenerThread(threading.Thread):
    def __init__(self, mqtt_client):
        threading.Thread.__init__(self)
        self.mqtt_client = mqtt_client

    def run(self):
        logger.info("Task Listener Thread started, waiting for incoming tasks.")
        self.mqtt_client.loop_forever()  # Blocking call for the MQTT loop


# Thread responsible for executing the tasks from the queue
class TaskExecutionThread(threading.Thread):
    def __init__(self, task_queue):
        threading.Thread.__init__(self)
        self.task_queue = task_queue

    def run(self):
        logger.info("Task Execution Thread started.")
        while True:
            yaml_filename = self.task_queue.get()
            if yaml_filename is None:
                logger.info("No task received. Exiting Task Execution Thread.")
                break
            self.process_task(yaml_filename)

    def process_task(self, yaml_filename):
        try:
            root_directory = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..")
            )
            config_directory = os.path.join(root_directory, "config")
            yaml_filepath = os.path.join(
                config_directory, os.path.basename(yaml_filename)
            )

            if not os.path.exists(yaml_filepath):
                logger.error(f"Configuration file not found: {yaml_filepath}")
                return

            logger.info(
                f"Preparing to build and run Prometheus. Configuration file located at {yaml_filepath}"
            )
            logger.info(f"Switching working directory to {config_directory}")
            os.chdir(config_directory)

            # Set up DockerClient with the YAML file as compose file
            docker_client = DockerClient(compose_files=[yaml_filepath])
            logger.info(f"Building and running containers with config: {yaml_filepath}")
            docker_client.compose.build()
            docker_client.compose.up(detach=True)
            logger.info("Docker-compose build and run completed successfully.")

            # Wait for the monitoring stack to be fully up
            logger.info("Checking if the monitoring stack is up and running...")
            while not is_monitoring_stack_up():
                logger.info("Waiting for monitoring stack services to start...")
                time.sleep(5)  # Retry every 5 seconds

            # Send system ready message to the coordinator
            send_system_ready()

        except FileNotFoundError:
            logger.error(f"File not found: {yaml_filepath}")
        except yaml.YAMLError as exc:
            logger.error(f"Error parsing YAML file: {exc}")
        except DockerException as e:
            logger.error(f"An error occurred with Docker: {e}")
        finally:
            logger.info("Task execution completed.")
            self.task_queue.task_done()


# Function to start the builder daemon
def main():
    # Set up the MQTT client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # Connect to the broker running on localhost
    mqtt_client.connect("localhost", 1883, 60)

    # Start the threads
    listener_thread = TaskListenerThread(mqtt_client)
    executor_thread = TaskExecutionThread(task_queue)

    listener_thread.start()
    executor_thread.start()

    listener_thread.join()
    executor_thread.join()


if __name__ == "__main__":
    main()
