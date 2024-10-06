import paho.mqtt.client as mqtt
import logging
import requests  # To make API calls to Prometheus
import yaml
import os
import json  # Import the json module
from dataclasses import dataclass
from typing import List, Optional

# Import the common logging configuration
from worker_node.utils import logging_config as log_config
from worker_node.utils.settings import cfg

# Set up the logger
logger = logging.getLogger("Monitor")
logger.setLevel(logging.INFO)  # Set the logging level

# Constants
MONITOR_TOPIC = "monitor/task"
QUERY_RESULTS_TOPIC = "monitor/results"

# Corrected URL for Prometheus API
PROMETHEUS_API_URL = cfg["prometheus"]["url"] + "/api/v1/query"
# Use the correct path for the queries file
QUERIES_FILE_PATH = cfg["queries"]["file_path"]


@dataclass
class Query:
    """Represents a single Prometheus query."""

    name: str
    expr: str
    measurement: Optional[str] = None
    tags: Optional[List[str]] = None
    fields: Optional[List[str]] = None


class CustomFormatter(logging.Formatter):
    """Custom formatter for structured logging."""

    def format(self, record):
        log_message = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "message": record.msg,
        }

        # If the message contains a dictionary (e.g., query results), format it nicely
        if isinstance(record.args, dict):
            log_message["details"] = record.args

        return json.dumps(log_message, indent=4)


class QueryManager:
    """Manages loading, executing, and formatting Prometheus queries."""

    def __init__(self, queries_file: str, mqtt_client: mqtt.Client):
        self.queries_file = queries_file
        self.mqtt_client = mqtt_client  # Store the MQTT client reference
        self.queries = self.load_queries()

    def load_queries(self) -> dict:
        """Load queries from the specified YAML file."""
        try:
            with open(self.queries_file, "r") as file:
                queries_data = yaml.safe_load(file)
            logger.info(
                f"Loaded {len(queries_data)} categories of queries from {self.queries_file}."
            )
            return queries_data
        except FileNotFoundError:
            logger.error(f"Queries file not found: {self.queries_file}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing queries file: {e}")
            return {}

    def execute_query(self, query: Query):
        """Send a query to Prometheus and return the results."""
        try:
            logger.info(
                f"Querying Prometheus for '{query.name}' with expr: {query.expr}"
            )
            # Log the URL being requested to help diagnose any issues
            logger.debug(
                f"Request URL: {PROMETHEUS_API_URL}, Parameters: { {'query': query.expr} }"
            )

            response = requests.get(
                PROMETHEUS_API_URL, params={"query": query.expr}, allow_redirects=True
            )

            # Log the actual URL of the response and any headers to track redirection
            logger.debug(
                f"Response URL: {response.url}, Status Code: {response.status_code}"
            )
            logger.debug(f"Response Headers: {response.headers}")
            logger.debug(
                f"Raw response from Prometheus: {response.text}"
            )  # Log the raw response

            # Check for HTTP status code 200
            if response.status_code != 200:
                logger.error(
                    f"Received non-200 status code from Prometheus: {response.status_code}"
                )
                logger.error(f"Response content: {response.text}")
                return None

            # Attempt to parse JSON response
            try:
                result = response.json()
                logger.info(f"Received response for query '{query.name}'")
                return result
            except json.JSONDecodeError as json_err:
                logger.error(
                    f"Failed to parse JSON response for '{query.name}': {json_err}"
                )
                logger.debug(
                    f"Raw response content: {response.text}"
                )  # Log the raw content for debugging
                return None

        except requests.RequestException as e:
            logger.error(f"Error querying Prometheus for '{query.name}': {e}")
            return None

    def format_results(self, query: Query, result: dict):
        """Format the results from the Prometheus query and send to MQTT."""
        formatted_result = {
            "query_name": query.name,
            "query_expr": query.expr,
            "results": [],
            "status": (
                "success"
                if result and "data" in result and "result" in result["data"]
                else "error"
            ),
        }

        if result and "data" in result and "result" in result["data"]:
            formatted_result["results"] = result["data"]["result"]
        else:
            logger.warning(
                f"No valid data in the results for query '{query.name}': {result}"
            )
            formatted_result["status"] = "error"

        # Publish the formatted results to the 'monitor/results' topic
        self.mqtt_client.publish("monitor/results", json.dumps(formatted_result), qos=1)
        logger.info(f"Published results for query '{query.name}': {formatted_result}")


class MonitorService:
    """Main monitoring service that handles MQTT messages and queries Prometheus."""

    def __init__(self, queries_file: str):
        self.mqtt_client = mqtt.Client()
        self.query_manager = QueryManager(
            queries_file, self.mqtt_client
        )  # Pass MQTT client to QueryManager
        self.prometheus_available = False  # To track Prometheus status

    def check_prometheus(self) -> bool:
        """Check if Prometheus is accessible."""
        try:
            # Updated URL for the health check
            response = requests.get(PROMETHEUS_API_URL, params={"query": "up"})
            response.raise_for_status()  # Will raise an error for bad status codes
            logger.info("Prometheus is accessible.")
            return True
        except requests.RequestException as e:
            logger.error(f"Prometheus is not accessible: {e}")
            return False

    def on_message(self, client, userdata, msg):
        """Handle receiving the monitoring task from coordinator."""
        payload = msg.payload.decode()
        logger.info(f"Received monitoring task: {payload}")

        # Check if Prometheus is available before executing any queries
        self.prometheus_available = self.check_prometheus()
        if not self.prometheus_available:
            logger.warning(
                "Skipping query execution since Prometheus is not available."
            )
            return  # Early exit if Prometheus is not available

        # Iterate over all the categories in the queries file and execute each query
        for category, queries in self.query_manager.queries.items():
            if isinstance(queries, dict):
                for sub_category, sub_queries in queries.items():
                    logger.info(f"Running queries for subcategory: {sub_category}")
                    if isinstance(sub_queries, list):
                        for query_data in sub_queries:
                            if isinstance(query_data, dict):
                                query = Query(
                                    name=query_data.get("name"),
                                    expr=query_data.get("expr"),
                                    measurement=query_data.get("measurement"),
                                    tags=query_data.get("tags"),
                                    fields=query_data.get("fields"),
                                )
                                result = self.query_manager.execute_query(query)
                                if result:
                                    self.query_manager.format_results(query, result)
                                else:
                                    logger.warning(
                                        f"No result returned for query: '{query.name}'"
                                    )
                            else:
                                logger.warning(
                                    f"Unexpected query format in subcategory '{sub_category}': {query_data}"
                                )
                    else:
                        logger.warning(
                            f"Unexpected queries format for subcategory '{sub_category}': {sub_queries}"
                        )
            else:
                logger.warning(
                    f"Unexpected queries format for category '{category}': {queries}"
                )

    def run(self):
        """Start the MQTT client and listen for tasks."""
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(
            cfg["mqtt"]["broker"], cfg["mqtt"]["port"], cfg["mqtt"]["keepalive"]
        )

        self.mqtt_client.subscribe(MONITOR_TOPIC, qos=1)
        logger.info(f"Subscribed to topic: {MONITOR_TOPIC}")

        # Start MQTT loop to listen for tasks
        self.mqtt_client.loop_forever()


def main():
    """Main function to initialize and run the monitoring service."""
    # Set up logging with custom formatter
    logging.basicConfig(level=logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    logger.addHandler(handler)

    # Initialize and run the monitor service
    service = MonitorService(QUERIES_FILE_PATH)
    service.run()


if __name__ == "__main__":
    main()
