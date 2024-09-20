import socket
import threading
import logging
import signal
import time

import settings

# Buffer size for the message queue
BUF_SIZE = 1024
# Status update interval in seconds
STATUS_UPDATE_INTERVAL = 30
# Address to send status updates to
STATUS_UPDATE_ADDR = ('127.0.0.1', 8888)  

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coordinator")

# Graceful shutdown flag
shutdown_flag = threading.Event()


def service_shutdown(signum, frame):
    """Handles shutdown signal"""
    logger.info(f"Caught signal {signum}. Shutting down.")
    shutdown_flag.set()
    # Ignore further SIGINT and SIGTERM signals
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)


class ListenerThread(threading.Thread):
    """
    Thread that listens for incoming messages and logs them.
    """
    def __init__(self, listen_socket, name="listener"):
        threading.Thread.__init__(self)
        self.listen_socket = listen_socket  # Socket for listening
        self.name = name  # Name of the thread

    def run(self) -> None:
        logger.info(f"Starting {self.name} thread.")
        while not shutdown_flag.is_set():
            try:
                # Listen for incoming messages
                msg, addr = self.listen_socket.recvfrom(BUF_SIZE)
                logger.info(f"Received message from {addr}: {msg.decode('utf-8')}")
            except socket.error as e:
                logger.error(f"Socket error: {e}")
            time.sleep(0.01)
        logger.info(f"Cleaning up {self.name} thread.")



class StatusUpdateThread(threading.Thread):
    """
    Thread that periodically sends status updates to a predefined address.
    """
    def __init__(self, send_socket, name="status_update"):
        """
        Initializes the StatusUpdateThread.
        
        :param send_socket: The socket object used for sending status updates.
        :param name: Name of the thread.
        """
        threading.Thread.__init__(self)
        self.send_socket = send_socket  # Socket for sending status updates
        self.name = name  # Name of the thread

    def run(self) -> None:
        """
        Runs the status update thread. Sends status updates periodically.
        """
        logger.info(f"Starting {self.name} thread.")
        while not shutdown_flag.is_set():
            try:
                # Status message to be sent
                status_message = "Coordinator is alive and well."
                self.send_socket.sendto(status_message.encode('utf-8'), STATUS_UPDATE_ADDR)
                logger.info(f"Sent status update to {STATUS_UPDATE_ADDR}")
            except socket.error as e:
                logger.error(f"Socket error: {e}")
            time.sleep(STATUS_UPDATE_INTERVAL)
        logger.info(f"Cleaning up {self.name} thread.")


def main():

    #  TODO: initialize this in program entry point 
    # Initialize settings
    settings.initialize()
    
    # Register the signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)

    try:
        # Create a UDP socket
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_addr = ('0.0.0.0', settings.socket_info['listen_port'])  # Listen on all interfaces, port 9999
        listen_sock.bind(listen_addr)

        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_addr = ('0.0.0.0', 0)  # Bind to a random port for sending status updates
        send_sock.bind(send_addr)

        # Create and start the threads
        listener = ListenerThread(listen_sock)
        status_updater = StatusUpdateThread(send_sock)

        threads = [listener, status_updater]

        for t in threads:
            t.start()

        # Keep the main thread running, checking the shutdown flag
        while not shutdown_flag.is_set():
            time.sleep(1)

    except settings.ServiceExit:
        logger.error("Begin to shutdown coordinatord.")
    finally:
          # Signal threads to shutdown
          shutdown_flag.set()
  
          # Shutdown & close sockets
          if listen_sock:
              listen_sock.close()
          if send_sock:
              send_sock.close()
  
          # Wait for the threads to close
          for t in threads:
              t.join()
          
          logger.info("Coordinator shutdown complete.")
  

if __name__ == "__main__":
    main()