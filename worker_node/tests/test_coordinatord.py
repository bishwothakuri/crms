import pytest
import jsonpickle
import queue
import time
from coordinatord.coordinatord import DispatcherThread

# Define the MockSocket here for testing purposes
class MockSocket:
    def __init__(self, data):
        self.data = data
        self.addr = ('127.0.0.1', 54321)

    def recvfrom(self, bufsize):
        return self.data, self.addr

    def settimeout(self, value):
        pass

@pytest.fixture
def job_queue():
    return queue.Queue()

@pytest.fixture
def mock_logger():
    class MockLogger:
        def info(self, msg):
            print(f"INFO: {msg}")

        def debug(self, msg):
            print(f"DEBUG: {msg}")

        def error(self, msg):
            print(f"ERROR: {msg}")

    return MockLogger()

def test_dispatcher_thread(job_queue, mock_logger):
    """
    Test the DispatcherThread to ensure it adds jobs to the queue.
    """
    # Mock a message from a worker node
    worker_info = {
        'type': 'REGISTER',
        'worker_info': {
            'hostname': 'worker1',
            'ip': '192.168.1.10',
            'cpu': '4 cores',
            'memory': '8GB'
        }
    }
    data = jsonpickle.encode(worker_info).encode('utf-8')

    # Mock the socket
    mock_socket = MockSocket(data)

    # Run DispatcherThread and ensure it stops after a short period
    dispatcher = DispatcherThread(job_queue, mock_socket, mock_logger, timeout=1)
    dispatcher.start()

    # Let the dispatcher run for a moment
    time.sleep(2)

    # Shut it down
    dispatcher.shutdown_flag.set()
    dispatcher.join()

    # Check if the job was added to the queue
    assert not job_queue.empty()
    job = job_queue.get()
    assert job['type'] == 'REGISTER'
    assert job['worker_info']['hostname'] == 'worker1'
