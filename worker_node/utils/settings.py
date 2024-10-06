# worker_node/utils/settings.py

import os
import sys
import yaml
import socket
import platform
import psutil
import pathlib

# Global variables to store configuration values
cfg = None
socket_info = None
broadcast_info = None

class ServiceExit(Exception):
    """Custom exception used to trigger the clean exit of all running threads and the main program."""
    pass

def initialize():
    """Initialize the configuration and system information."""
    main_path = str(pathlib.Path(__file__).parent.absolute())
    
    # Load settings from YAML configuration
    global cfg
    with open(os.path.join(main_path, 'settings.yml'), 'r') as f:
        try:
            cfg = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(f"Error loading settings.yml: {exc}")
            return

    global socket_info
    global broadcast_info

    af_map = {
        socket.AF_INET: 'IPv4',
    }

    # Get hostname and interface name based on the system configuration
    hostname = platform.uname()[1]
    interface_name = cfg['system'].get('main_interface', 'eth0')
    ipv4_addr = None
    ipv4_broadcast_addr = None

    # Find IPv4 and broadcast addresses of the primary interface
    for nic, addrs in psutil.net_if_addrs().items():
        if nic == interface_name:
            for addr in addrs:
                if af_map.get(addr.family) == 'IPv4':
                    ipv4_addr = addr.address
                    if addr.broadcast:
                        ipv4_broadcast_addr = addr.broadcast

    # Set socket information based on the configuration and detected addresses
    if ipv4_addr:
        broadcast_info = {
            'direct_broadcast_addr': ipv4_broadcast_addr if ipv4_broadcast_addr else '',
            'limited_broadcast_addr': '255.255.255.255',
            'worker_dest_port': cfg['coordinatord']['worker_dest_port'],
            'monitor_dest_port': cfg['coordinatord']['monitor_dest_port']
        }
        socket_info = {
            'hostname': hostname,
            'inet_addr': ipv4_addr,
            'listen_port': cfg['coordinatord']['listen_port'],
            'send_port': cfg['coordinatord']['send_port'],
            'broadcast_port': cfg['coordinatord']['broadcast_port'],
            'query_send_port': cfg['queryd']['send_port'],
            'onos_port': cfg['queryd']['onos_port']
        }
    else:
        print("Cannot get required system information. Shutdown system now!")
        sys.exit(1)

# Initialize settings on module import
initialize()
