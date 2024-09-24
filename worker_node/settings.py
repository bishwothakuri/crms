import multiprocessing

import enum
import sys
import jsonpickle
import psutil
import socket
import dtos
import yaml
import pathlib
import os
import platform
from utilities import HostTinyDbWrapper, QueryCriteriaTinyDbWrapper

cfg = None
socket_info = None
broadcast_info = None
host_db_manager = None
query_db_manager = None
collector_ready = multiprocessing.Event()


class ServiceExit(Exception):
    """
    Custom exception which is used to trigger the clean exit
    of all running threads and the main program.
    """
    pass


class JsonCrmPktTypeHandler(jsonpickle.handlers.BaseHandler):
    def restore(self, obj):
        pass

    def flatten(self, obj: enum.Enum, data):
        return obj.name


def initialize():
    """
    Initialize the global variables used in various modules/classes/processes
    :return:
    """
    main_path = str(pathlib.Path(__file__).parent.absolute())
    global cfg
    with open(os.path.join(main_path, 'config.yml'), 'r') as f:
        try:
            cfg = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(exc)

    # debug
    # print(cfg)

    global socket_info
    global broadcast_info

    af_map = {
        socket.AF_INET: 'IPv4',
    }

    hostname = None
    if cfg['system']['type'] == 'simulation':
        hostname = os.environ.get('HOSTNAME', 'default_hostname')
        interface_name = hostname + '-eth0'
    else:
        hostname = platform.uname()[1]
        interface_name = cfg['system']['main_interface']

    ipv4_addr = None
    ipv4_broadcast_addr = None

    # find ipv4 and broadcast addresses of the primary interface
    for nic, addrs in psutil.net_if_addrs().items():
        if nic == interface_name:
            for addr in addrs:
                if af_map.get(addr.family) == 'IPv4':
                    ipv4_addr = addr.address
                    if addr.broadcast:
                        ipv4_broadcast_addr = addr.broadcast

    if ipv4_addr:
        broadcast_info = {
            'direct_broadcast_addr': ipv4_broadcast_addr if ipv4_broadcast_addr is not None else '',
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
        print("Cannot get required system information. Shutdown collector system now!")
        sys.exit(1)

    # register new enum handler for jsonpickle
    jsonpickle.handlers.registry.register(dtos.CrmPktType, JsonCrmPktTypeHandler)

    # initialize tinydb managers
    global host_db_manager
    global query_db_manager
    global_db_access_lock = multiprocessing.Lock()
    host_db_manager = HostTinyDbWrapper(os.path.join(main_path, 'host_db.json'), global_db_access_lock)
    query_db_manager = QueryCriteriaTinyDbWrapper(os.path.join(main_path, 'criteria_db.json'), global_db_access_lock)
