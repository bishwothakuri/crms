# builderd.py

import os
import time
import paho.mqtt.client as mqtt
import logging
import threading
import queue
import traceback
from python_on_whales import docker, DockerException

# Import the centralized logging configuration, settings, and message module
from utils.logging_config import configure_logging
from utils.message import Message, MessageType
from utils import settings

# Configure logging
configure_logging()
logger = logging.getLogger("Builderd")


class MqttHandler:
    """Handles MQTT client setup, connection, and message publishing."""

    def __init__(self, broker, port, keepalive, build_topic, on_message_callback):
        self.broker = broker
        self.port = port
        self.keepalive = keepalive
        self.build_topic = build_topic
        self.mqtt_client = mqtt.Client()
        self.on_message_callback = on_message_callback

    def initialize(self):
        """Initialize the MQTT client and connect to the broker."""
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message_callback
        self.mqtt_client.connect(self.broker, self.port, self.keepalive)
        self.mqtt_client.subscribe(self.build_topic, qos=1)
        logger.info(f"Subscribed to topic: {self.build_topic}")

    def on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT client connects to the broker."""
        if rc == 0:
            logger.info("Successfully connected to MQTT Broker.")
        else:
            logger.error(f"Failed to connect to MQTT Broker, return code {rc}")

    def start(self):
        """Start the MQTT client loop."""
        self.mqtt_client.loop_start()

    def stop(self):
        """Stop the MQTT client loop."""
        self.mqtt_client.loop_stop()

    def publish_message(self, topic, message):
        """Publish a message to the specified topic."""
        self.mqtt_client.publish(topic, message, qos=1)
        logger.info(f"Published message to topic: {topic}, message: {message}")


class DockerManager:
    """Handles Docker-related operations such as pulling images and running containers."""

    def __init__(self, monitoring_stack):
        self.monitoring_stack = monitoring_stack

    def pull_images(self):
        """Pull images from Docker Hub."""
        try:
            for service in self.monitoring_stack:
                image_name = service['image']
                logger.info(f"Pulling image: {image_name}")
                docker.image.pull(image_name)
            logger.info("Successfully pulled all images.")
            return True
        except DockerException as e:
            logger.error(f"Error pulling images: {e}")
            return False

    def run_containers(self):
        """Run containers based on the monitoring stack configuration."""
        try:
            # Ensure the network exists
            self.create_network('monitoring-net')
    
            for service in self.monitoring_stack:
                container_name = service['container_name']
                image_name = service['image']
                ports_dict = service.get('ports', {})
                volumes_list = service.get('volumes', [])
                environment = service.get('environment', {})  # Ensure it's a dict
                command = service.get('command')
                networks = service.get('networks', [])
                privileged = service.get('privileged', False)
    
                # Convert ports to list of tuples
                ports = []
                for host_port, container_port in ports_dict.items():
                    ports.append((str(host_port), str(container_port)))
    
                # Convert volumes to list of tuples with absolute paths
                volumes = []
                script_dir = os.path.dirname(os.path.abspath(__file__))
                for volume_mapping in volumes_list:
                    parts = volume_mapping.split(':')
                    if len(parts) == 2:
                        host_volume, container_volume = parts
                        mode = None
                    elif len(parts) == 3:
                        host_volume, container_volume, mode = parts
                    else:
                        logger.error(f"Invalid volume format: {volume_mapping}")
                        continue
                    
                    # Convert host_volume to absolute path if it's a relative path
                    if not os.path.isabs(host_volume):
                        host_volume_abs = os.path.abspath(os.path.join(script_dir, host_volume))
                    else:
                        host_volume_abs = host_volume
    
                    # Check if the path exists
                    if not os.path.exists(host_volume_abs):
                        logger.error(f"Host path '{host_volume_abs}' does not exist for volume mount.")
                        continue  # Skip this volume mount or handle accordingly
                    
                    # Build the volume tuple
                    if mode:
                        volumes.append((host_volume_abs, container_volume, mode))
                    else:
                        volumes.append((host_volume_abs, container_volume))
    
                # Log the formatted ports and volumes for debugging
                logger.debug(f"Ports for container '{container_name}': {ports}")
                logger.debug(f"Volumes for container '{container_name}': {volumes}")
                logger.debug(f"Networks for container '{container_name}': {networks}")
                logger.debug(f"Command for container '{container_name}': {command}")
                logger.debug(f"Environment for container '{container_name}': {environment}")
    
                # Remove existing container if it exists
                existing_containers = docker.ps(all=True, filters={"name": container_name})
                if existing_containers:
                    logger.info(f"Container '{container_name}' already exists. Removing it.")
                    docker.remove(container_name, force=True)
    
                # Run the container
                logger.info(f"Running container '{container_name}'")
                # Build kwargs for docker.run
                run_kwargs = {
                    'name': container_name,
                    'detach': True,
                    'restart': 'unless-stopped',
                    'privileged': privileged,
                }
                if ports:
                    run_kwargs['publish'] = ports
                if volumes:
                    run_kwargs['volumes'] = volumes
                if environment:
                    run_kwargs['envs'] = environment
                if command:
                    run_kwargs['command'] = command
                if networks:
                    run_kwargs['networks'] = networks
    
                logger.info(f"docker.run arguments: {image_name}, {run_kwargs}")
                docker.run(image_name, **run_kwargs)
    
            logger.info("Successfully started all containers.")
            return True
        except DockerException as e:
            logger.error(f"Error running containers: {e}")
            traceback_str = traceback.format_exc()
            logger.error(f"Traceback: {traceback_str}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            traceback_str = traceback.format_exc()
            logger.error(f"Traceback: {traceback_str}")
            return False

    def create_network(self, network_name):
        """Create a Docker network if it doesn't exist."""
        networks = docker.network.list()
        if network_name not in [net.name for net in networks]:
            logger.info(f"Creating network '{network_name}'")
            docker.network.create(network_name)
        else:
            logger.info(f"Network '{network_name}' already exists.")

    def is_stack_up(self):
        """Check if all the monitoring stack services are up and running."""
        try:
            for service in self.monitoring_stack:
                container_name = service['container_name']
                container = docker.container.inspect(container_name)
                if not container.state.running:
                    logger.info(f"Service '{container_name}' is not running yet.")
                    return False
            return True
        except DockerException as e:
            logger.error(f"Error checking service status: {e}")
            return False


class TaskExecutionThread(threading.Thread):
    """Thread responsible for executing tasks received by the Builder Daemon."""

    def __init__(self, task_queue, builder_daemon):
        super().__init__()
        self.task_queue = task_queue
        self.builder_daemon = builder_daemon
        self.shutdown_flag = threading.Event()

    def run(self):
        """Run the thread to process tasks."""
        logger.info("Task Execution Thread started.")
        while not self.shutdown_flag.is_set():
            try:
                # Use blocking call with timeout instead of empty check
                message = self.task_queue.get(timeout=0.1)
                self.process_task(message)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in TaskExecutionThread: {e}")
                traceback_str = traceback.format_exc()
                logger.error(f"Traceback: {traceback_str}")

    def process_task(self, message: Message):
        """Process and execute the build task."""
        logger.info(f"Processing task: {message.task_id}")
        if self.builder_daemon.docker_manager.pull_images():
            if self.builder_daemon.docker_manager.run_containers():
                start_time = time.time()
                timeout = 300  # Timeout in seconds (5 minutes)
                while not self.builder_daemon.docker_manager.is_stack_up():
                    if time.time() - start_time > timeout:
                        logger.error("Timeout waiting for monitoring stack services to start.")
                        return
                    logger.info("Waiting for monitoring stack services to start...")
                    time.sleep(5)

                # Send system ready message once the stack is confirmed to be ready
                self.builder_daemon.send_system_ready_message()
        logger.info("Task execution completed.")


class Builder:
    """Builder class to manage task execution and communication with the Coordinator."""

    def __init__(self):
        # Load configurations from settings
        self.cfg = settings.cfg
        self.task_queue = queue.Queue()
        self.task_execution_thread = None

        # Setup MQTT handler
        self.mqtt_handler = MqttHandler(
            broker=self.cfg['mqtt']['broker'],
            port=self.cfg['mqtt']['port'],
            keepalive=self.cfg['mqtt']['keepalive'],
            build_topic=self.cfg['topics']['build_task'],
            on_message_callback=self.on_message,
        )

        # Setup Docker manager
        self.docker_manager = DockerManager(
            monitoring_stack=self.cfg['builderd']['monitoring_stack'],
        )

    def on_message(self, client, userdata, msg):
        """Callback when a message is received on the subscribed topics."""
        try:
            payload = msg.payload.decode()
            message = Message.from_json(payload)
            logger.info(f"Received build task: {message.content.get('config_file', 'unknown file')}")

            # Put the received build task into the task queue for processing
            self.task_queue.put(message)
        except Exception as e:
            logger.error(f"Error processing received message: {e}")

    def send_system_ready_message(self):
        """Send a system ready message to the Coordinator once the monitoring stack is up."""
        try:
            message = Message(
                type=MessageType.STATUS,
                task_id="system-status-001",
                content={"status": "Monitoring stack is up. System is ready."}
            )
            self.mqtt_handler.publish_message(self.cfg['topics']['coordinator'], message.to_json())
            logger.info(f"Sent system ready message to Coordinator: {message}")
        except Exception as e:
            logger.error(f"Failed to send system ready message: {e}")

    def start_task_execution_thread(self):
        """Start the task execution thread."""
        self.task_execution_thread = TaskExecutionThread(self.task_queue, self)
        self.task_execution_thread.start()

    def stop_task_execution_thread(self):
        """Stop the task execution thread."""
        if self.task_execution_thread:
            self.task_execution_thread.shutdown_flag.set()
            self.task_execution_thread.join()

    def run(self):
        """Run the Builder daemon service."""
        self.mqtt_handler.initialize()
        self.mqtt_handler.start()
        self.start_task_execution_thread()

        try:
            while True:
                time.sleep(1)  # Keep the main loop alive to maintain MQTT connection
        except KeyboardInterrupt:
            logger.info("Shutting down Builder Daemon.")
            self.stop_task_execution_thread()
            self.mqtt_handler.stop()


def main():
    """Main function to initialize and run the Builder Daemon."""
    # Create and run the Builder daemon service
    builder_daemon = Builder()
    builder_daemon.run()


if __name__ == "__main__":
    main()
