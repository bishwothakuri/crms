import threading
import queue
import time
import paho.mqtt.client as mqtt
import logging

# Constants for MQTT topics
BUILD_TOPIC = "build/task"
MONITOR_TOPIC = "monitor/task"
TASK_QUEUE_SIZE = 10

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Coordinator")

# Task Queue
task_queue = queue.Queue(maxsize=TASK_QUEUE_SIZE)


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
                    if task['type'] == 'build':
                        logger.info(f"Sending build task to Builder: {task}")
                        self.mqtt_client.publish(BUILD_TOPIC, task['config_file'], qos=1)

                    # Send to monitor subscriber if it's a monitoring task
                    elif task['type'] == 'monitor':
                        logger.info(f"Sending monitor task to Monitor: {task}")
                        self.mqtt_client.publish(MONITOR_TOPIC, task['config_file'], qos=1)

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
    # Initialize MQTT client
    mqtt_client = mqtt.Client()
    mqtt_client.connect("localhost", 1883, 60)

    # Start the task distribution thread
    task_distribution_thread = TaskDistributionThread(mqtt_client)
    task_control_thread = TaskControlThread()

    # Start both threads
    task_distribution_thread.start()
    task_control_thread.start()

    # Simulate adding a unique task once, without repeating continuously
    task = {'type': 'build', 'config_file': 'config/monitoring-stack-docker-compose.yml'}
    
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


if __name__ == "__main__":
    main()
