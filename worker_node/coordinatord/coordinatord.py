import jsonpickle
import logging
import socket
import threading
import queue
import time
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


def main():
    logger = logging.getLogger("coordinator")
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    listen_sock.bind(('0.0.0.0', settings.socket_info['listen_port']))

    in_queue = queue.Queue(BUF_SIZE)

    # Start DispatcherThread
    dispatcher = DispatcherThread(in_queue, listen_sock, logger)
    dispatcher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Coordinator Daemon.")
        dispatcher.shutdown_flag.set()
        dispatcher.join()

if __name__ == "__main__":
    main()
