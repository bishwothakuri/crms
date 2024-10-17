import os
import time
import paho.mqtt.client as mqtt
import logging
import threading
import queue
from python_on_whales import DockerClient, DockerException

# Import the centralized logging configuration, settings, and message module
from worker_node.utils.logging_config import configure_logging
from worker_node.utils import settings
from worker_node.utils.message import Message, MessageType

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
    """Handles Docker-related operations such as building and running containers."""
    def __init__(self, monitoring_stack, monitoring_stack_file):
        self.monitoring_stack = monitoring_stack
        self.monitoring_stack_file = monitoring_stack_file

    def build_and_run_stack(self):
        """Build and run Docker Compose stack based on the provided configuration file."""
        try:
            config_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), "../monitoring_config"))
            yaml_filepath = os.path.join(config_directory, self.monitoring_stack_file)

            if not os.path.exists(yaml_filepath):
                logger.error(f"Configuration file not found: {yaml_filepath}")
                return False

            logger.info(f"Starting to build and run containers with config: {yaml_filepath}")
            docker_client = DockerClient(compose_files=[yaml_filepath])
            docker_client.compose.build(services=None)  # Build all services
            docker_client.compose.up(detach=True)
            logger.info("Docker-compose build and run completed successfully.")
            return True
        except DockerException as e:
            logger.error(f"An error occurred with Docker: {e}")
            return False

    def is_stack_up(self):
        """Check if all the monitoring stack services are up and running."""
        try:
            for service in self.monitoring_stack:
                container = DockerClient.container.inspect(service)
                if not container.state.running:
                    logger.info(f"Service {service} is not running yet.")
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

    def process_task(self, message: Message):
        """Process and execute the build task."""
        logger.info(f"Processing task: {message.task_id}")
        if self.builder_daemon.docker_manager.build_and_run_stack():
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
            monitoring_stack_file=self.cfg['builderd']['monitoring_stack_file'],
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
