import paho.mqtt.client as mqtt
import logging
import requests  # To make API calls to Prometheus
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Monitor")

# Constants
MONITOR_TOPIC = "monitor/task"
PROMETHEUS_API_URL = "http://localhost:9090/api/v1/query"  # Change this if Prometheus is not on localhost

# Function to query Prometheus
def query_prometheus(query):
    """Send a query to the Prometheus API and return the results."""
    try:
        logger.info(f"Querying Prometheus: {query}")
        response = requests.get(PROMETHEUS_API_URL, params={"query": query})
        response.raise_for_status()  # Raise exception for HTTP errors
        result = response.json()
        logger.info(f"Prometheus Response Received for Query: {query}")
        return result
    except requests.RequestException as e:
        logger.error(f"Error querying Prometheus: {e}")
        return None

# Function to format the Prometheus results for better readability
def format_prometheus_results(query, result):
    """Format the Prometheus query result for readable logging."""
    if result and result.get('status') == 'success':
        logger.info(f"Results for query '{query}':")
        for item in result['data']['result']:
            metric = item['metric']
            value = item['value']
            metric_info = ', '.join([f"{key}: {val}" for key, val in metric.items()])
            logger.info(f"  Metric: {metric_info} | Value: {value[1]}")
    else:
        logger.warning(f"No valid results for query '{query}'.")

# Function to handle incoming monitoring tasks
def on_message(client, userdata, msg):
    """Handle receiving the monitoring task from coordinator."""
    payload = msg.payload.decode()
    logger.info(f"Received monitoring task: {payload}")

    # Query Prometheus for some metrics (modify query based on what you want to monitor)
    cpu_query = "rate(node_cpu_seconds_total[5m])"
    memory_query = "node_memory_MemAvailable_bytes"
    
    # Get CPU usage data
    cpu_data = query_prometheus(cpu_query)
    if cpu_data:
        format_prometheus_results(cpu_query, cpu_data)
    
    # Get memory usage data
    memory_data = query_prometheus(memory_query)
    if memory_data:
        format_prometheus_results(memory_query, memory_data)

def main():
    # Initialize MQTT client
    mqtt_client = mqtt.Client()
    mqtt_client.on_message = on_message
    mqtt_client.connect("localhost", 1883, 60)

    mqtt_client.subscribe(MONITOR_TOPIC, qos=1)
    logger.info(f"Subscribed to topic: {MONITOR_TOPIC}")

    # Start MQTT loop to listen for tasks
    mqtt_client.loop_forever()

if __name__ == "__main__":
    main()
