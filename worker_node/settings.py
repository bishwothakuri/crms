from multiprocessing import Lock

import enum
import jsonpickle
import psutil
import socket
import dtos
import yaml
import pathlib
import os
import platform

cfg = None
socket_info = None
collector_info = None
api_endpoint = None


class ServiceExit(Exception):
    """
    Custom exception which is used to trigger the clean exit
    of all running threads and the main program.
    """
    pass


class WorkerState(enum.Enum):
    INITIALIZED = 1
    REGISTERING = 2
    REGISTERED = 3
    REGISTER_FAILED = 4


worker_state = WorkerState.INITIALIZED
state_lock = Lock()

def service_shutdown(signum, frame):
    print('Caught signal %d' % signum)
    raise ServiceExit


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
    global api_endpoint

    af_map = {
        socket.AF_INET: 'IPv4',
    }

    hostname = None
    if cfg['system']['type'] == 'simulation':
        hostname = os.environ.get('HOSTNAME')
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

    socket_info = {
        'hostname': hostname,
        'inet_addr': ipv4_addr if ipv4_addr is not None else '0.0.0.0',
        'listen_port': cfg['workerd']['listen_port'],
        'send_port': cfg['workerd']['send_port'],
        'builderd_port': cfg['builderd']['listen_port']
    }

    api_endpoint = cfg['builderd']['api_endpoint']

    # register new enum handler for jsonpickle
    jsonpickle.handlers.registry.register(dtos.CrmPktType, JsonCrmPktTypeHandler)


def check_worker_state(state: 'WorkerState') -> bool:
    with state_lock:
        global worker_state
        return worker_state == state


def update_worker_state(state: 'WorkerState'):
    with state_lock:
        global worker_state
        worker_state = state
