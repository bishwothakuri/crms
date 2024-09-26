import os
import paho.mqtt.client as mqtt
import yaml
import subprocess
import logging
import threading
import queue
from python_on_whales import docker, DockerException, DockerClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Builderd")

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
            # Get the absolute path for the config directory
            root_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            config_directory = os.path.join(root_directory, 'config')
    
            print("Hello world", config_directory)
    
            yaml_filepath = os.path.join(config_directory, os.path.basename(yaml_filename))
    
            # Check if the file exists in the 'config' directory
            if not os.path.exists(yaml_filepath):
                logger.error(f"Configuration file not found: {yaml_filepath}")
                return
    
            logger.info(f"Preparing to build and run Prometheus. Configuration file located at {yaml_filepath}")
            logger.info(f"Switching working directory to {config_directory}")
            os.chdir(config_directory)
    
            # Set up DockerClient with the YAML file as compose file
            docker_client = DockerClient(compose_files=[yaml_filepath])
    
            # Build and run the Docker containers using python-on-whales (docker compose)
            logger.info(f"Building and running containers with config: {yaml_filepath}")
            docker_client.compose.build()  # Build the services
            docker_client.compose.up(detach=True)  # Bring up the services in detached mode
            logger.info("Docker-compose build and run completed successfully.")
    
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
def start_builder():
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
    start_builder()
