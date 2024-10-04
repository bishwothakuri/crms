import argparse
import logging
from worker_node import builderd, coordinatord, monitord  # Import the service modules
from worker_node.common import logging_config as log_config

# Set up logging configuration for the CLI
logger = logging.getLogger(__name__)

# Dictionary mapping service names to their respective modules
SERVICES = {
    'builderd': builderd.main,
    'coordinatord': coordinatord.main,
    'monitord': monitord.main,
}

def run_service(service_name: str):
    """Run the specified service."""
    if service_name in SERVICES:
        logger.info(f"Starting {service_name} service...")
        SERVICES[service_name]()
    else:
        logger.error(f"Service '{service_name}' not recognized. Available services: {', '.join(SERVICES.keys())}")


def main():
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Worker Node CLI for managing different services.")
    parser.add_argument(
        'service',
        choices=SERVICES.keys(),
        help="The service to run. Options: 'builderd', 'coordinatord', 'monitord'."
    )
    args = parser.parse_args()

    # Run the specified service
    run_service(args.service)


if __name__ == '__main__':
    main()
