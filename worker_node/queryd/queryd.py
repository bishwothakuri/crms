import logging
from typing import Dict
import json
import jsonpickle
import requests
import signal
import socket
import threading
import time
import queue
import paho.mqtt.client as mqtt
from datetime import datetime

# Import the common logging configuration
from utils.logging_config import configure_logging
from utils import settings
from utils.settings import cfg

# Configure logging
configure_logging()
logger = logging.getLogger("Queryd")


# Buffer size for queues
BUF_SIZE = 10000

# Use configurations from settings module
# MQTT Configuration
MQTT_BROKER = cfg['mqtt']['broker']
MQTT_PORT = cfg['mqtt']['port']
QUERY_RESULTS_TOPIC = "monitor/results"  # Updated topic to receive query results from `monitord`

# UDP Configuration for ONOS Controller
ONOS_CONTROLLER_ADDR = settings.broadcast_info['limited_broadcast_addr']
ONOS_CONTROLLER_PORT = settings.socket_info['onos_port']

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QueryD")


def service_shutdown(signum, frame):
    """Handle shutdown signal for graceful service exit."""
    print(f'Caught signal {signum}')
    raise settings.ServiceExit


def parse_query_response(json_data):
    """Parse the response of a query and extract important values."""
    if json_data['status'] == 'success':
        query_result = []
        report_defaults = {
            'measurement': json_data.get('measurement', json_data.get('query_name', 'measurement')),
            'tags': json_data.get('tags', []),
            'fields': json_data.get('fields', []),
            'cookies': 'influx_report'  # Use default or adjust as needed
        }

        for result in json_data['results']:
            query_report = {
                'type': report_defaults['cookies'],
                'measurement': report_defaults['measurement'],
                'tag_set': [],
                'field_set': [],
                'timestamp': None
            }

            # Handle tags
            if report_defaults['tags']:
                for tag in report_defaults['tags']:
                    if tag in result['metric']:
                        query_report['tag_set'].append(f'{tag}={result["metric"][tag]}')
            else:
                # If no tags specified, use all available metric labels
                for k, v in result['metric'].items():
                    query_report['tag_set'].append(f'{k}={v}')

            # Handle fields
            if report_defaults['fields']:
                for field in report_defaults['fields']:
                    query_report['field_set'].append(f'{field}={result["value"][1]}')
            else:
                # If no fields specified, use a default field name
                query_report['field_set'].append(f'value={result["value"][1]}')

            query_report['timestamp'] = result['value'][0]
            query_result.append(query_report)

        return query_result
    else:
        return None


def write_to_iql_file(report: Dict) -> None:
    """
    Write to iql file
    :param report:
    :return:
    """
    with open("rmtb.txt", "a") as f:
        tags = ','.join(report['tag_set'])
        fields = ','.join(report['field_set'])
        f.write('{},{} {} {}\n'.format(report['measurement'],
                                       tags,
                                       fields,
                                       str(report['timestamp'])))


class QueryManagerThread(threading.Thread):
    """Thread to manage incoming query results and parse them for sending to ONOS."""
    
    def __init__(self, in_queue: queue.Queue, out_queue: queue.Queue, logger, name="query_manager"):
        threading.Thread.__init__(self)
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.logger = logger
        self.name = name
        self.shutdown_flag = threading.Event()

    def run(self):
        """Main thread logic for managing and processing query results."""
        self.logger.info(f"Starting {self.name} thread.")
        while not self.shutdown_flag.is_set():
            if not self.in_queue.empty():
                message = self.in_queue.get()
                query_result = json.loads(message)  # Parse the incoming message as JSON

                # Extract fields from the message
                if 'results' in query_result:
                    reports = parse_query_response(query_result)

                    # Place the parsed report in the output queue for the QuerySenderThread
                    if reports:
                        for report in reports:
                            # write to iql file (debug only)
                            write_to_iql_file(report)
                            self.out_queue.put({'type': 'onos', 'report': report})

                self.in_queue.task_done()

            time.sleep(0.1)
        self.logger.info(f"Cleaning up {self.name} thread.")


class QuerySenderThread(threading.Thread):
    """Thread to send parsed query results to the ONOS controller."""
    
    def __init__(self, in_queue: queue.Queue, send_socket: socket.socket, logger, name="query_sender"):
        threading.Thread.__init__(self)
        self.in_queue = in_queue
        self.send_socket = send_socket
        self.logger = logger
        self.name = name
        self.shutdown_flag = threading.Event()

    def run(self):
        """Main thread logic for sending parsed reports to the ONOS controller."""
        self.logger.info(f"Starting {self.name} thread.")
        while not self.shutdown_flag.is_set():
            if not self.in_queue.empty():
                send_job = self.in_queue.get()
                if send_job['type'] == 'onos':
                    # Serialize the report and send it to the ONOS controller via UDP
                    report_data = jsonpickle.encode(send_job['report'], unpicklable=False)
                    try:
                        self.send_socket.sendto(report_data.encode('utf-8'), (ONOS_CONTROLLER_ADDR, ONOS_CONTROLLER_PORT))
                        self.logger.info(f"Sent report to ONOS controller: {send_job['report']}")
                    except PermissionError as e:
                        self.logger.error(f"PermissionError while sending data: {e}")
                    except Exception as e:
                        self.logger.error(f"Unexpected error while sending data: {e}")
                self.in_queue.task_done()

            time.sleep(0.1)
        self.logger.info(f"Cleaning up {self.name} thread.")


class QueryDaemon:
    """QueryDaemon class to handle MQTT integration and manage query processing and sending."""
    
    def __init__(self, broker: str, port: int, query_results_topic: str):
        self.broker = broker
        self.port = port
        self.query_results_topic = query_results_topic
        self.mqtt_client = mqtt.Client()
        self.report_queue = queue.Queue(BUF_SIZE)
        self.parsed_queue = queue.Queue(BUF_SIZE)

        self.query_manager = None
        self.query_sender = None
        self.send_socket = self.create_udp_socket()

    def create_udp_socket(self):
        """Create and return a UDP socket with broadcasting enabled."""
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Enable broadcasting mode
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return udp_socket

    def initialize_mqtt(self):
        """Initialize the MQTT client, set callbacks, and connect to broker."""
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(self.broker, self.port, 60)
        self.mqtt_client.subscribe(self.query_results_topic, qos=1)  # Subscribing to the correct topic
        logger.info(f"Subscribed to topic: {self.query_results_topic}")

    def on_connect(self, client, userdata, flags, rc):
        """Callback when the MQTT client connects to the broker."""
        if rc == 0:
            logger.info("Successfully connected to MQTT Broker.")
        else:
            logger.error(f"Failed to connect to MQTT Broker, return code {rc}")

    def on_message(self, client, userdata, msg):
        """Handle messages received on the subscribed MQTT topics."""
        try:
            payload = msg.payload.decode()
            logger.info(f"Received query result from topic '{msg.topic}': {payload}")
            # Put the received query result into the report queue for processing
            self.report_queue.put(payload)
        except Exception as e:
            logger.error(f"Error processing received message: {e}")

    def run(self):
        """Run the QueryDaemon service."""
        self.initialize_mqtt()
        self.mqtt_client.loop_start()

        # Create and start QueryManagerThread and QuerySenderThread
        self.query_manager = QueryManagerThread(in_queue=self.report_queue, out_queue=self.parsed_queue, logger=logger)
        self.query_sender = QuerySenderThread(in_queue=self.parsed_queue, send_socket=self.send_socket, logger=logger)
        
        self.query_manager.start()
        self.query_sender.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down Query Daemon.")
            self.query_manager.shutdown_flag.set()
            self.query_sender.shutdown_flag.set()
            self.query_manager.join()
            self.query_sender.join()
            self.mqtt_client.loop_stop()


def main():
    """Main function to initialize and run the Query Daemon."""
    # Use settings from settings.py instead of hardcoded values
    query_daemon = QueryDaemon(
        broker=settings.cfg['mqtt']['broker'], 
        port=settings.cfg['mqtt']['port'], 
        query_results_topic=QUERY_RESULTS_TOPIC
    )
    query_daemon.run()


if __name__ == "__main__":
    main()
