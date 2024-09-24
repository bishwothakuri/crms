import sys
import os
import jsonpickle
import logging
import socket
import threading
import queue
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settings

BUF_SIZE = 1000

class DispatcherThread(threading.Thread):
    """
    Listens for messages from worker nodes and places them in the job queue.
    """
    def __init__(self, job_queue, listen_socket, logger, timeout=2):
        threading.Thread.__init__(self)
        self.job_queue = job_queue
        self.listen_socket = listen_socket
        self.logger = logger
        self.shutdown_flag = threading.Event()
        self.timeout = timeout

    def run(self):
        self.logger.info("Dispatcher Thread started.")
        while not self.shutdown_flag.is_set():
            try:
                # Receive message from worker node
                msg, addr = self.listen_socket.recvfrom(1024)
                # Decode the message
                job = jsonpickle.decode(msg)
                # Add the job to the queue
                while self.job_queue.full():
                    time.sleep(0.01)  # Wait if the queue is full
                self.job_queue.put(job)
                self.logger.debug(f"Received job: {job['type']} from {addr}")
            except Exception as e:
                self.logger.error(f"Error in DispatcherThread: {e}")
            time.sleep(0.01)

        self.logger.info("Dispatcher Thread shutting down.")


class CoordinatorManagerThread(threading.Thread):
    """
    Handles worker registration, task assignments, and manages worker heartbeats.
    """

    def __init__(self, job_queue, monitor_queue, builder_queue, logger, self_init_flag=False):
        threading.Thread.__init__(self)
        self.job_queue = job_queue
        self.monitor_queue = monitor_queue
        self.builder_queue = builder_queue
        self.logger = logger
        self.shutdown_flag = threading.Event()
        self.self_init_flag = self_init_flag
        self.host_db_manager = settings.host_db_manager

    def run(self):
        self.logger.info("Coordinator Manager Thread started.")
        # Handle self-registration if SELF_INITIALIZE is true
        if self.self_init_flag:
            self.logger.info("Self-Registration for this node.")
            self.self_initialize()

        while not self.shutdown_flag.is_set():
            if not self.job_queue.empty():
                job = self.job_queue.get()

                if job["type"] == "REGISTER":
                    self.handle_worker_registration(job["worker_info"])

                elif job["type"] == "BUILD_TASK":
                    self.handle_build_task(job["worker_info"])

            time.sleep(0.01)

        self.logger.info("Coordinator Manager Thread shutting down.")

    def self_initialize(self):
        """
        Perform self-registration (as the worker node) when the node starts.
        """
        worker_info = {
            "hostname": settings.socket_info["hostname"],
            "inet_addr": settings.socket_info["inet_addr"],
            "port": settings.socket_info["listen_port"]
        }
        self.handle_worker_registration(worker_info)

    def handle_worker_registration(self, worker_info):
        """
        Register worker nodes and handle heartbeats with improved logging.
        """
        self.logger.info(f"Attempting to register worker: {worker_info}")
        try:
            is_host_existed = self.host_db_manager.check_host_existence(worker_info["hostname"])

            if not is_host_existed:
                self.logger.info(f"Worker {worker_info['hostname']} not found in DB, attempting to register.")
                success = settings.host_db_manager.insert_host(worker_info)
                if success:
                    self.logger.info(f"Worker {worker_info['hostname']} registered successfully.")
                    self.monitor_queue.put(
                        {"type": "START_MONITORING", "worker_info": worker_info}
                    )
                else:
                    self.logger.error(f"Failed to register worker: {worker_info['hostname']}. Check DB insertion logic.")
            else:
                self.logger.info(f"Worker {worker_info['hostname']} exists. Updating heartbeat.")
                self.host_db_manager.update_host_heartbeat(worker_info["hostname"])
        except Exception as e:
            self.logger.error(f"Exception during worker registration: {e}")
            raise e

    def handle_build_task(self, worker_info):
        """
        Delegate build tasks to the builder daemon.
        """
        self.logger.info(f"Delegating build task to builder for worker: {worker_info['hostname']}")
        self.builder_queue.put({"type": "START_BUILD", "worker_info": worker_info})


def main():
    logger = logging.getLogger("coordinator")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    listen_sock.bind(("0.0.0.0", settings.socket_info["listen_port"]))

    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock.bind(("0.0.0.0", settings.socket_info["send_port"]))

    in_queue = queue.Queue(BUF_SIZE)
    monitor_queue = queue.Queue(BUF_SIZE)
    builder_queue = queue.Queue(BUF_SIZE)

    dispatcher = DispatcherThread(in_queue, listen_sock, logger)

    # Pass self_init_flag=True to enable self-registration
    coordinator_manager = CoordinatorManagerThread(
        in_queue, monitor_queue, builder_queue, logger, self_init_flag=True
    )

    threads = [dispatcher, coordinator_manager]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Coordinator Daemon.")
        for t in threads:
            t.shutdown_flag.set()
        for t in threads:
            t.join()


if __name__ == "__main__":
    settings.initialize()  # Ensure settings are loaded
    main()
