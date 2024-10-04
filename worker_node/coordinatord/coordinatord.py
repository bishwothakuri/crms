import threading
import queue
import json
import time
import paho.mqtt.client as mqtt
import logging
import socket

# Import the common logging configuration
from worker_node.common import logging_config as log_config

# Create a logger specific to this module
logger = logging.getLogger("Coordinator")

# Constants for MQTT topics
BUILD_TOPIC = "build/task"
MONITOR_TOPIC = "monitor/task"
TASK_QUEUE_SIZE = 10
REGISTER_MESSAGE = "REGISTER"
ACK_MESSAGE = "ACK"
CRMA_IP = "127.0.0.1"
CRMA_UDP_PORT = 12345
COORDINATOR_UDP_PORT = 54321
MAX_RETRIES = 20  # Maximum number of retries for sending REGISTER

# Task Queue
task_queue = queue.Queue(maxsize=TASK_QUEUE_SIZE)


# UDP Socket for Coordinator
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(("", COORDINATOR_UDP_PORT))  # Bind to the local port for receiving ACK


def send_register_to_crma():
    """Send a REGISTER UDP packet to the CRMA."""
    try:
        register_data = REGISTER_MESSAGE.encode()
        udp_socket.sendto(register_data, (CRMA_IP, CRMA_UDP_PORT))
        logger.info(f"Sent REGISTER message to CRMA at {CRMA_IP}:{CRMA_UDP_PORT}")
    except socket.error as e:
        logger.error(f"Failed to send REGISTER message to CRMA: {e}")


def wait_for_ack_from_crma():
    """Wait for the ACK message from the CRMA."""
    try:
        udp_socket.settimeout(5)
        data, _ = udp_socket.recvfrom(1024)
        message = data.decode()
        if message == ACK_MESSAGE:
            logger.info(
                "Received ACK message from CRMA. Proceeding to task initiation."
            )
            return True
        else:
            logger.warning(f"Received unexpected message from CRMA: {message}")
            return False
    except socket.timeout:
        logger.error("Timeout waiting for ACK from CRMA. Retrying...")
    except socket.error as e:
        logger.error(f"Socket error while waiting for ACK from CRMA: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
    return False


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        logger.info(f"Received message from {payload['sender']}: {payload['content']}")

        if payload["sender"] == "builderd" and payload["type"] == "status":
            if payload["content"] == "Monitoring stack is up. System is ready.":
                logger.info("Monitoring stack is ready, preparing monitoring task.")
                task = {
                    "type": "monitor",
                    "config_file": "config/monitoring-stack-docker-compose.yml",
                }
                task_queue.put(task)
                logger.info(f"Added monitor task to queue: {task}")
    except json.JSONDecodeError:
        logger.error("Error decoding message.")


class TaskDistributionThread(threading.Thread):
    """
    Thread responsible for distributing tasks (publishing messages).
    """

    def __init__(self, mqtt_client):
        threading.Thread.__init__(self)
        self.mqtt_client = mqtt_client
        self.shutdown_flag = threading.Event()

    def run(self):
        logger.info("Task Distribution Thread started.")
        while not self.shutdown_flag.is_set():
            try:
                # If there is a task in the queue, process it
                if not task_queue.empty():
                    task = task_queue.get()

                    # Send to builder subscriber if it's a build task
                    if task["type"] == "build":
                        logger.info(f"Sending build task to Builder: {task}")
                        self.mqtt_client.publish(
                            BUILD_TOPIC, task["config_file"], qos=1
                        )

                    # Send to monitor subscriber if it's a monitoring task
                    elif task["type"] == "monitor":
                        logger.info(f"Sending monitor task to Monitor: {task}")
                        self.mqtt_client.publish(
                            MONITOR_TOPIC, task["config_file"], qos=1
                        )

                    # Mark the task as done only after processing
                    task_queue.task_done()
                else:
                    time.sleep(0.1)  # Avoid busy waiting
            except Exception as e:
                logger.error(f"Error in TaskDistributionThread: {e}")
                continue


class TaskControlThread(threading.Thread):
    """
    Thread responsible for controlling task retries and task completion checks.
    """

    def __init__(self):
        threading.Thread.__init__(self)
        self.shutdown_flag = threading.Event()

    def run(self):
        logger.info("Task Control Thread started.")
        while not self.shutdown_flag.is_set():
            # This could check if tasks have completed and handle retries
            logger.info("Controlling tasks (e.g., checking completion, retries)")
            time.sleep(5)


def main():

    retries = 0
    while retries < MAX_RETRIES:
        send_register_to_crma()
        if wait_for_ack_from_crma():
            break
        retries += 1
        if retries < MAX_RETRIES:
            logger.info(f"Retrying ({retries}/{MAX_RETRIES})...")
        else:
            logger.error(
                f"Failed to receive ACK from CRMA after {MAX_RETRIES} attempts. Exiting..."
            )
            return

    # Initialize MQTT client
    mqtt_client = mqtt.Client()
    mqtt_client.on_message = on_message
    mqtt_client.connect("localhost", 1883, 60)

    mqtt_client.subscribe("builder/coordinator", qos=1)
    logger.info("Subscribed to topic: builder/coordinator")

    # Start the MQTT loop to handle incoming messages
    mqtt_client.loop_start()

    # Start the task distribution thread
    task_distribution_thread = TaskDistributionThread(mqtt_client)
    task_control_thread = TaskControlThread()

    # Start both threads
    task_distribution_thread.start()
    task_control_thread.start()

    # Simulate adding a unique task once, without repeating continuously
    task = {
        "type": "build",
        "config_file": "config/monitoring-stack-docker-compose.yml",
    }

    if task_queue.qsize() == 0:  # Add only if the queue is empty
        task_queue.put(task)
        logger.info(f"Added task to queue: {task}")

    try:
        # Keep the main loop alive to maintain MQTT connection
        while True:
            time.sleep(1)  # Just wait for any interruptions or external triggers
    except KeyboardInterrupt:
        logger.info("Shutting down Coordinator.")
        task_distribution_thread.shutdown_flag.set()
        task_control_thread.shutdown_flag.set()
        task_distribution_thread.join()
        task_control_thread.join()
        # Stop the MQTT loop
        mqtt_client.loop_stop()


if __name__ == "__main__":
    main()
