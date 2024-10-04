import paho.mqtt.client as mqtt
import logging
import requests  # To make API calls to Prometheus
import yaml
import os
from dataclasses import dataclass
from typing import List, Optional

# Import the common logging configuration
from worker_node.common import logging_config as log_config

# Set up the logger
logger = logging.getLogger("Monitor")

# Constants
MONITOR_TOPIC = "monitor/task"
PROMETHEUS_API_URL = "http://localhost:9090/api/v1/query"
QUERIES_FILE_PATH = os.path.join(os.path.dirname(__file__), "../config/queries.yml")


@dataclass
class Query:
    """Represents a single Prometheus query."""
    name: str
    expr: str
    measurement: Optional[str] = None
    tags: Optional[List[str]] = None
    fields: Optional[List[str]] = None


class QueryManager:
    """Manages loading, executing, and formatting Prometheus queries."""
    
    def __init__(self, queries_file: str):
        self.queries_file = queries_file
        self.queries = self.load_queries()
    
    def load_queries(self) -> dict:
        """Load queries from the specified YAML file."""
        try:
            with open(self.queries_file, "r") as file:
                queries_data = yaml.safe_load(file)
            logger.info(f"Loaded {len(queries_data)} categories of queries from {self.queries_file}.")
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
            logger.info(f"Querying Prometheus for '{query.name}' with expr: {query.expr}")
            response = requests.get(PROMETHEUS_API_URL, params={"query": query.expr})
            response.raise_for_status()
            result = response.json()
            logger.info(f"Received response for query '{query.name}'")
            return result
        except requests.RequestException as e:
            logger.error(f"Error querying Prometheus for '{query.name}': {e}")
            return None

    def format_results(self, query: Query, result: dict):
        """Format the results of a Prometheus query."""
        if result and result.get("status") == "success":
            logger.info(f"Results for query '{query.name}':")
            for item in result["data"]["result"]:
                metric = item["metric"]
                value = item["value"]
                metric_info = ", ".join([f"{key}: {val}" for key, val in metric.items()])
                logger.info(f"  Metric: {metric_info} | Value: {value[1]}")
        else:
            logger.warning(f"No valid results for query '{query.name}'.")


class MonitorService:
    """Main monitoring service that handles MQTT messages and queries Prometheus."""

    def __init__(self, queries_file: str):
        self.query_manager = QueryManager(queries_file)

    def on_message(self, client, userdata, msg):
        """Handle receiving the monitoring task from coordinator."""
        payload = msg.payload.decode()
        logger.info(f"Received monitoring task: {payload}")

        # Iterate over all the categories in the queries file and execute each query
        for category, queries in self.query_manager.queries.items():
            logger.info(f"Running queries for category: {category}")
            if isinstance(queries, list):
                for query_data in queries:
                    if isinstance(query_data, dict):
                        query = Query(
                            name=query_data.get("name"),
                            expr=query_data.get("expr"),
                            measurement=query_data.get("measurement"),
                            tags=query_data.get("tags"),
                            fields=query_data.get("fields")
                        )
                        result = self.query_manager.execute_query(query)
                        if result:
                            self.query_manager.format_results(query, result)
                    else:
                        logger.warning(f"Unexpected query format in category '{category}': {query_data}")
            else:
                logger.warning(f"Unexpected queries format for category '{category}': {queries}")

    def run(self):
        """Start the MQTT client and listen for tasks."""
        mqtt_client = mqtt.Client()
        mqtt_client.on_message = self.on_message
        mqtt_client.connect("localhost", 1883, 60)

        mqtt_client.subscribe(MONITOR_TOPIC, qos=1)
        logger.info(f"Subscribed to topic: {MONITOR_TOPIC}")

        # Start MQTT loop to listen for tasks
        mqtt_client.loop_forever()


def main():
    service = MonitorService(QUERIES_FILE_PATH)
    service.run()


if __name__ == "__main__":
    main()
