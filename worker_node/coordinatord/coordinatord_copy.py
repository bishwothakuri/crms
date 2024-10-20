import threading
import queue
import time
import socket
import paho.mqtt.client as mqtt
import logging
from enum import Enum

# Import the centralized logging configuration, settings, and message module
from worker_node.utils.logging_config import configure_logging
from worker_node.utils.message import Message, MessageType
from worker_node.utils import settings

# Configure logging
configure_logging()
logger = logging.getLogger("Coordinator")


class CoordinatorState(Enum):
    """Enum to represent the states of the Coordinator."""
    INITIALIZING = 1
    REGISTERED = 2
    BUILD_TASK_SENT = 3
    MONITORING_READY = 4
    COMPLETED = 5


class MqttHandler:
    """Handles MQTT client setup, connection, and message publishing."""
    def __init__(self, broker_address, mqtt_port, mqtt_keepalive, coordinator_topic, on_message_callback):
        self.broker_address = broker_address
        self.mqtt_port = mqtt_port
        self.mqtt_keepalive = mqtt_keepalive
        self.coordinator_topic = coordinator_topic
        self.mqtt_client = mqtt.Client()
        self.on_message_callback = on_message_callback

    def initialize(self):
        """Initialize and set up the MQTT client."""
        self.mqtt_client.on_message = self.on_message_callback
        self.mqtt_client.connect(self.broker_address, self.mqtt_port, self.mqtt_keepalive)
        self.mqtt_client.subscribe(self.coordinator_topic, qos=1)
        logger.info(f"Subscribed to topic: {self.coordinator_topic}")

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


class CRMACommunicator:
    """Handles UDP communication with CRMA."""
    def __init__(self, crma_ip, crma_udp_port, coordinator_udp_port, ack_message, max_retries):
        self.crma_ip = crma_ip
        self.crma_udp_port = crma_udp_port
        self.ack_message = ack_message
        self.max_retries = max_retries
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(("", coordinator_udp_port))

    def send_register_message(self, register_message):
        """Send register message to CRMA."""
        try:
            message = register_message.encode()
            self.udp_socket.sendto(message, (self.crma_ip, self.crma_udp_port))
            logger.info(f"Sent register message to CRMA at {self.crma_ip}:{self.crma_udp_port}")
            return True
        except socket.error as e:
            logger.error(f"Failed to send register message to CRMA: {e}")
            return False

    def wait_for_ack(self, timeout=5):
        """Wait for the ACK message from CRMA."""
        try:
            self.udp_socket.settimeout(timeout)
            data, _ = self.udp_socket.recvfrom(1024)
            if data.decode() == self.ack_message:
                logger.info("Received ACK message from CRMA. Registration successful.")
                return True
            else:
                logger.warning(f"Received unexpected message from CRMA: {data.decode()}")
        except socket.timeout:
            logger.warning("Timeout waiting for ACK from CRMA.")
        except socket.error as e:
            logger.error(f"Socket error while waiting for ACK from CRMA: {e}")
        return False

    def register_with_crma(self, register_message):
        """Register with CRMA, retrying up to `max_retries` times if necessary."""
        for attempt in range(1, self.max_retries + 1):
            if self.send_register_message(register_message) and self.wait_for_ack():
                return True
            logger.info(f"Retrying registration with CRMA ({attempt}/{self.max_retries})...")
            time.sleep(1)
        logger.error(f"Failed to register with CRMA after {self.max_retries} attempts.")
        return False


class TaskDistributionThread(threading.Thread):
    """Thread responsible for distributing tasks (publishing messages)."""
    def __init__(self, mqtt_client, task_queue, build_topic, monitor_topic):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.task_queue = task_queue
        self.build_topic = build_topic
        self.monitor_topic = monitor_topic
        self.shutdown_flag = threading.Event()
        self.task_ready = threading.Event()  # Event to signal that tasks are ready

    def run(self):
        logger.info("Task Distribution Thread started.")
        while not self.shutdown_flag.is_set():
            # Wait until a task is ready or the thread is shutting down
            self.task_ready.wait()
            self.task_ready.clear()

            while not self.task_queue.empty():
                try:
                    task = self.task_queue.get()

                    # Send the serialized message to builder or monitor subscriber
                    if task.type == MessageType.BUILD:
                        logger.info(f"Sending build task to Builder: {task.task_id}, service={task.content['service']}")
                        self.mqtt_client.publish(self.build_topic, task.to_json(), qos=1)
                    elif task.type == MessageType.MONITOR:
                        logger.info(f"Sending monitor task to Monitor: {task.task_id}, target={task.content['target']}")
                        self.mqtt_client.publish(self.monitor_topic, task.to_json(), qos=1)

                    self.task_queue.task_done()
                except Exception as e:
                    logger.error(f"Error in TaskDistributionThread: {e}")
                    continue
        logger.info("Task Distribution Thread stopped.")


class Coordinator:
    """Coordinator class to manage communication between CRMA, builderd, and monitord services."""
    def __init__(self):
        # Load configurations from settings
        self.cfg = settings.cfg

        # Coordinator state
        self.state = CoordinatorState.INITIALIZING
        self.state_change_event = threading.Event()

        # Set up CRMA communicator
        self.crma_communicator = CRMACommunicator(
            crma_ip=self.cfg['coordinatord']['crma_ip'],
            crma_udp_port=self.cfg['coordinatord']['crma_udp_port'],
            coordinator_udp_port=self.cfg['coordinatord']['udp_port'],
            ack_message=self.cfg['coordinatord']['ack_message'],
            max_retries=self.cfg['coordinatord']['max_retries'],
        )

        # Set up MQTT handler
        self.mqtt_handler = MqttHandler(
            broker_address=self.cfg['mqtt']['broker'],
            mqtt_port=self.cfg['mqtt']['port'],
            mqtt_keepalive=self.cfg['mqtt']['keepalive'],
            coordinator_topic=self.cfg['topics']['coordinator'],
            on_message_callback=self.on_message,
        )

        # Task settings
        self.build_topic = self.cfg['topics']['build_task']
        self.monitor_topic = self.cfg['topics']['monitor_task']
        self.task_queue = queue.Queue(maxsize=self.cfg['coordinatord']['task_queue_size'])
        self.task_distribution_thread = None

    def set_state(self, new_state):
        """Set the state and trigger the state change event."""
        self.state = new_state
        logger.info(f"State changed to: {self.state}")
        self.state_change_event.set()  # Notify all listeners about the state change

    def send_build_task(self):
        """Send the build task to the builder service."""
        build_task = Message(
            type=MessageType.BUILD,
            task_id="build-task-001",
            content={
                "service": "monitoring_stack",
                "config_file": "config/monitoring-stack-docker-compose.yml",
            },
        )
        self.task_queue.put(build_task)  # Enqueue the build task
        self.task_distribution_thread.task_ready.set()  # Signal that a task is ready
        logger.info(f"Build task queued: task_id={build_task.task_id}, service={build_task.content['service']}")
        self.set_state(CoordinatorState.BUILD_TASK_SENT)

    def send_monitor_task(self):
        """Send the monitor task to the monitor service."""
        monitor_task = Message(
            type=MessageType.MONITOR,
            task_id="monitor-task-001",
            content={"target": "system-metrics", "interval": "10s"},
        )
        self.task_queue.put(monitor_task)  # Enqueue the monitor task
        self.task_distribution_thread.task_ready.set()  # Signal that a task is ready
        logger.info(f"Monitor task queued: task_id={monitor_task.task_id}, target={monitor_task.content['target']}")

    def on_message(self, client, userdata, msg):
        """Callback function for handling messages received from MQTT."""
        try:
            payload = msg.payload.decode()
            message = Message.from_json(payload)
            logger.info(f"Received message from {message.task_id}: {message.content}")

            if (
                message.type == MessageType.STATUS
                and "Monitoring stack is up" in message.content.get("status", "")
            ):
                logger.info("Monitoring stack is up and ready. Proceeding with monitor task.")
                self.set_state(CoordinatorState.MONITORING_READY)
        except Exception as e:
            logger.error(f"Error processing received message: {e}")

    def start_task_distribution_thread(self):
        """Start the task distribution thread."""
        self.task_distribution_thread = TaskDistributionThread(
            self.mqtt_handler.mqtt_client, self.task_queue, self.build_topic, self.monitor_topic
        )
        self.task_distribution_thread.start()

    def stop_task_distribution_thread(self):
        """Stop the task distribution thread."""
        if self.task_distribution_thread:
            self.task_distribution_thread.shutdown_flag.set()
            self.task_distribution_thread.task_ready.set()  # Unblock the thread if waiting
            self.task_distribution_thread.join()
            logger.info("Task distribution thread has been stopped.")

    def run(self):
        """Run the Coordinator service."""
        if not self.crma_communicator.register_with_crma(self.cfg['coordinatord']['register_message']):
            return

        self.mqtt_handler.initialize()
        self.mqtt_handler.start()

        # Start the task distribution thread
        self.start_task_distribution_thread()

        # Send build task first
        self.send_build_task()

        # Wait for acknowledgment from builder that monitoring stack is up
        self.state_change_event.clear()
        while self.state != CoordinatorState.MONITORING_READY:
            logger.info("Waiting for monitoring stack to be ready...")
            self.state_change_event.wait(2)

        # Send monitor task only after the stack is confirmed to be ready
        self.send_monitor_task()

        try:
            while True:
                time.sleep(1)  # Keep the main loop alive to maintain MQTT connection
        except KeyboardInterrupt:
            logger.info("Shutting down Coordinator.")
            self.stop_task_distribution_thread()
            self.mqtt_handler.stop()


def main():
    """Main function to initialize and run the Coordinator."""
    # Create and run the Coordinator service
    coordinator = Coordinator()
    coordinator.run()


if __name__ == "__main__":
    main()
