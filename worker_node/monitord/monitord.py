import paho.mqtt.client as mqtt
import logging
import requests  # To make API calls to Prometheus
import yaml
import json  # Import the json module
from typing import List, Optional, Dict

# Import the common logging configuration
from utils import logging_config as log_config
from utils.settings import cfg

# Set up the logger
logger = logging.getLogger("Monitor")

# Use logging level from settings
log_level = getattr(logging, cfg["logging"]["level"].upper(), logging.INFO)
logger.setLevel(log_level)

# Constants from configuration
MONITOR_TOPIC = cfg["topics"]["monitor_task"]
QUERY_RESULTS_TOPIC = cfg["topics"]["query_results"]

# Corrected URL for Prometheus API
PROMETHEUS_API_URL = (
    cfg["prometheus"]["url"] + "/api/v1/%query_type%?query=%query_expr%%query_params%"
)
# Path for the queries file
QUERIES_FILE_PATH = cfg["queries"]["file_path"]

# Default interval from settings
DEFAULT_INTERVAL = cfg.get("prom_queries", {}).get("default_interval", "1m")


def assemble_query(
    based_query_url: str, query_conf: Dict, filters: List[Dict], **kwargs
) -> Dict:
    """
    Build a complete URL for a resource consumption query based on Prometheus API structure.
    """
    url = based_query_url
    param_defaults = {"time": None, "timeout": None}

    # Update param_defaults if needed
    param_defaults.update(kwargs)

    # Get the type of query's expression
    url = url.replace("%query_type%", query_conf["type"])

    # Build the complete of query's expression
    expr = query_conf["expr"]

    # Add filters (if required)
    if "%filters%" in expr and filters:
        filter_expr = ""
        edited_criteria = []
        for criterion in filters:
            edited_criteria.append(
                '{}{}"{}"'.format(
                    criterion["field_name"],
                    criterion["regex"],
                    criterion["field_value"],
                )
            )
        filter_expr += ",".join(edited_criteria)

        expr = expr.replace("%filters%", filter_expr)
    else:
        expr = expr.replace("%filters%", "")

    # Add extras (if required)
    if "%extras%" in expr:
        extras_value = ",".join(query_conf["extras"]) if "extras" in query_conf else ""
        expr = expr.replace("%extras%", extras_value)
    else:
        expr = expr.replace("%extras%", "")

    # Add interval (if required)
    if "%interval%" in expr:
        expr = expr.replace("%interval%", query_conf.get("interval", DEFAULT_INTERVAL))

    # Add tags (if needed)
    if "%tags%" in expr and query_conf.get("tags"):
        tags_expr = ",".join(query_conf["tags"])
        expr = expr.replace("%tags%", tags_expr)

    # Replace the query expression in the URL
    url = url.replace("%query_expr%", requests.utils.quote(expr))

    param_values = ""

    # Build query_params
    for k, v in param_defaults.items():
        if v:
            param_values += "&" + str(k) + "=" + str(v)

    # Replace params
    url = url.replace("%query_params%", param_values)

    return {
        "url": url,
        "name": query_conf["name"],
        "report_conf": {
            "measurement": query_conf.get("measurement"),
            "tags": query_conf.get("tags"),
            "fields": query_conf.get("fields"),
            "timestamp": param_defaults.get("time"),
        },
    }


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

            # Adjusted to access the categories correctly
            queries = queries_data.get("prom_queries", {}).get("category", {})
            logger.info(
                f"Loaded {len(queries)} categories of queries from {self.queries_file}."
            )
            return queries
        except FileNotFoundError:
            logger.error(f"Queries file not found: {self.queries_file}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing queries file: {e}")
            return {}

    def execute_query(self, query_conf: Dict, filters: List[Dict]):
        """Assemble and send a query to Prometheus and return the results."""
        try:
            # Assemble the query
            assembled_query = assemble_query(PROMETHEUS_API_URL, query_conf, filters)

            query_url = assembled_query["url"]
            query_name = assembled_query["name"]

            logger.info(f"Querying Prometheus for '{query_name}' with URL: {query_url}")

            response = requests.get(query_url, allow_redirects=True)

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
                logger.info(f"Received response for query '{query_name}'")
                return result
            except json.JSONDecodeError as json_err:
                logger.error(
                    f"Failed to parse JSON response for '{query_name}': {json_err}"
                )
                logger.debug(
                    f"Raw response content: {response.text}"
                )  # Log the raw content for debugging
                return None

        except requests.RequestException as e:
            logger.error(f"Error querying Prometheus for '{query_conf['name']}': {e}")
            return None

    def format_results(self, query_name: str, query_expr: str, result: dict):
        """Format the results from the Prometheus query and send to MQTT."""
        formatted_result = {
            "query_name": query_name,
            "query_expr": query_expr,
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
                f"No valid data in the results for query '{query_name}': {result}"
            )
            formatted_result["status"] = "error"

        # Publish the formatted results to the configured topic
        self.mqtt_client.publish(
            QUERY_RESULTS_TOPIC, json.dumps(formatted_result), qos=1
        )
        logger.info(f"Published results for query '{query_name}': {formatted_result}")


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
            health_url = (
                PROMETHEUS_API_URL.replace("%query_type%", "query")
                .replace("%query_expr%", "up")
                .replace("%query_params%", "")
            )
            response = requests.get(health_url)
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

        # Define filters if any (you may need to parse them from payload or settings)
        filters = []  # For now, we assume no filters; adjust as needed

        # Iterate over all the categories in the queries file and execute each query
        for category, queries in self.query_manager.queries.items():
            if isinstance(queries, list):
                for query_data in queries:
                    if isinstance(query_data, dict):
                        query_conf = query_data  # Use the query configuration directly
                        result = self.query_manager.execute_query(query_conf, filters)
                        if result:
                            self.query_manager.format_results(
                                query_conf["name"], query_conf["expr"], result
                            )
                        else:
                            logger.warning(
                                f"No result returned for query: '{query_conf['name']}'"
                            )
                    else:
                        logger.warning(
                            f"Unexpected query format in category '{category}': {query_data}"
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
    logging.basicConfig(level=log_level)
    handler = logging.StreamHandler()
    logger.addHandler(handler)

    # Initialize and run the monitor service
    service = MonitorService(QUERIES_FILE_PATH)
    service.run()


if __name__ == "__main__":
    main()
