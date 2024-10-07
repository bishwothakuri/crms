# worker_node/coordinatord/coordinatord.py

import threading
import queue
import time
import socket
import paho.mqtt.client as mqtt
import logging

# Import the centralized logging configuration, settings, and message module
from worker_node.utils.logging_config import configure_logging
from worker_node.utils.message import Message, MessageType
from worker_node.utils import settings

# Configure logging
configure_logging()
logger = logging.getLogger("Coordinator")


class Coordinator:
    """Coordinator class to manage communication between CRMA and worker nodes."""

    def __init__(self):
        # Load configurations from settings
        self.cfg = settings.cfg
        self.broker_address = self.cfg['mqtt']['broker']
        self.mqtt_port = self.cfg['mqtt']['port']
        self.mqtt_keepalive = self.cfg['mqtt']['keepalive']

        self.build_topic = self.cfg['topics']['build_task']
        self.monitor_topic = self.cfg['topics']['monitor_task']
        self.coordinator_topic = self.cfg['topics']['coordinator']

        self.coordinator_udp_port = self.cfg['coordinatord']['udp_port']
        self.crma_ip = self.cfg['coordinatord']['crma_ip']
        self.crma_udp_port = self.cfg['coordinatord']['crma_udp_port']
        self.max_retries = self.cfg['coordinatord']['max_retries']
        self.task_queue_size = self.cfg['coordinatord']['task_queue_size']
        self.register_message = self.cfg['coordinatord']['register_message']
        self.ack_message = self.cfg['coordinatord']['ack_message']

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(("", self.coordinator_udp_port))
        self.mqtt_client = mqtt.Client()
        self.task_queue = queue.Queue(maxsize=self.task_queue_size)
        self.task_distribution_thread = None
        self.build_task_sent = False
        self.monitor_stack_ready = False

    def initialize_mqtt(self):
        """Initialize the MQTT client and set up callbacks."""
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(
            self.broker_address, self.mqtt_port, self.mqtt_keepalive
        )
        self.mqtt_client.subscribe(self.coordinator_topic, qos=1)
        logger.info(f"Subscribed to topic: {self.coordinator_topic}")

    def send_register_to_crma(self):
        """Send a REGISTER UDP packet to the CRMA."""
        try:
            register_data = self.register_message.encode()
            self.udp_socket.sendto(register_data, (self.crma_ip, self.crma_udp_port))
            logger.info(
                f"Sent REGISTER message to CRMA at {self.crma_ip}:{self.crma_udp_port}"
            )
        except socket.error as e:
            logger.error(f"Failed to send REGISTER message to CRMA: {e}")

    def wait_for_ack_from_crma(self):
        """Wait for the ACK message from the CRMA."""
        try:
            self.udp_socket.settimeout(5)
            data, _ = self.udp_socket.recvfrom(1024)
            message = data.decode()
            if message == self.ack_message:
                logger.info(
                    "Received ACK message from CRMA. Proceeding to task initiation."
                )
                return True
            else:
                logger.warning(f"Received unexpected message from CRMA: {message}")
        except socket.timeout:
            logger.warning("Timeout waiting for ACK from CRMA. Retrying...")
        except socket.error as e:
            logger.error(f"Socket error while waiting for ACK from CRMA: {e}")
        except Exception as e:
            logger.error(f"Unexpected error occurred: {e}")
        return False

    def register_with_crma(self, max_retries: int):
        """Register with CRMA, retrying up to `max_retries` times if necessary."""
        retries = 0
        while retries < max_retries:
            self.send_register_to_crma()
            if self.wait_for_ack_from_crma():
                return True
            retries += 1
            logger.info(f"Retrying registration ({retries}/{max_retries})...")

        logger.error(
            f"Failed to receive ACK from CRMA after {max_retries} attempts. Exiting..."
        )
        return False

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
        self.mqtt_client.publish(self.build_topic, build_task.to_json(), qos=1)
        logger.info(f"Sent build task to Builder: {build_task}")
        self.build_task_sent = True

    def send_monitor_task(self):
        """Send the monitor task to the monitor service."""
        monitor_task = Message(
            type=MessageType.MONITOR,
            task_id="monitor-task-001",
            content={"target": "system-metrics", "interval": "10s"},
        )
        self.mqtt_client.publish(self.monitor_topic, monitor_task.to_json(), qos=1)
        logger.info(f"Sent monitor task to Monitor: {monitor_task}")

    def on_message(self, client, userdata, msg):
        """Callback function for handling messages received from MQTT."""
        try:
            payload = msg.payload.decode()
            message = Message.from_json(payload)
            logger.info(f"Received message from {message.task_id}: {message.content}")

            # Handle messages and update state based on message type
            if (
                message.type == MessageType.STATUS
                and "Monitoring stack is up" in message.content.get("status", "")
            ):
                logger.info("Received acknowledgment that monitoring stack is ready.")
                self.monitor_stack_ready = True
        except Exception as e:
            logger.error(f"Error processing received message: {e}")

    def start_task_distribution_thread(self):
        """Start the task distribution thread."""
        self.task_distribution_thread = TaskDistributionThread(
            self.mqtt_client, self.task_queue, self.build_topic, self.monitor_topic
        )
        self.task_distribution_thread.start()

    def stop_task_distribution_thread(self):
        """Stop the task distribution thread."""
        if self.task_distribution_thread:
            self.task_distribution_thread.shutdown_flag.set()
            self.task_distribution_thread.join()

    def run(self):
        """Run the Coordinator service."""
        if not self.register_with_crma(self.max_retries):
            return

        self.initialize_mqtt()
        self.mqtt_client.loop_start()

        # Send build task first
        self.send_build_task()

        # Wait for acknowledgment from builder that monitoring stack is up
        while not self.monitor_stack_ready:
            logger.info("Waiting for monitoring stack to be ready...")
            time.sleep(2)

        # Send monitor task only after the stack is confirmed to be ready
        self.send_monitor_task()

        self.start_task_distribution_thread()

        try:
            while True:
                time.sleep(1)  # Keep the main loop alive to maintain MQTT connection
        except KeyboardInterrupt:
            logger.info("Shutting down Coordinator.")
            self.stop_task_distribution_thread()
            self.mqtt_client.loop_stop()


class TaskDistributionThread(threading.Thread):
    """Thread responsible for distributing tasks (publishing messages)."""

    def __init__(self, mqtt_client, task_queue, build_topic, monitor_topic):
        super().__init__()
        self.mqtt_client = mqtt_client
        self.task_queue = task_queue
        self.build_topic = build_topic
        self.monitor_topic = monitor_topic
        self.shutdown_flag = threading.Event()

    def run(self):
        logger.info("Task Distribution Thread started.")
        while not self.shutdown_flag.is_set():
            try:
                if not self.task_queue.empty():
                    task = self.task_queue.get()

                    # Send the serialized message to builder or monitor subscriber
                    if task.type == MessageType.BUILD:
                        logger.info(f"Sending build task to Builder: {task}")
                        self.mqtt_client.publish(self.build_topic, task.to_json(), qos=1)

                    elif task.type == MessageType.MONITOR:
                        logger.info(f"Sending monitor task to Monitor: {task}")
                        self.mqtt_client.publish(self.monitor_topic, task.to_json(), qos=1)

                    self.task_queue.task_done()
                else:
                    time.sleep(0.1)  # Avoid busy waiting
            except Exception as e:
                logger.error(f"Error in TaskDistributionThread: {e}")
                continue


def main():
    """Main function to initialize and run the Coordinator."""
    # Create and run the Coordinator service
    coordinator = Coordinator()
    coordinator.run()


if __name__ == "__main__":
    main()
