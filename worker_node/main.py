import settings as settings

# call only once
settings.initialize()

import logging
import logging.handlers
from multiprocessing import Process, Queue


def setup_logger():
    log = logging.getLogger("root")
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s - %(filename)-20s:%(lineno)-5d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    return log


setup_logger()
if __name__ == '__main__':
    logger_name = 'root'
    logger = logging.getLogger(logger_name)
    logger.info("Starting worker nodes")
    processes = []

    import coordinator


    # create a queue between coordinator and builder
    cord_to_builder_queue = Queue
    # create a queue between coordinator and monitor
    cord_to_monitor_queue = Queue

    # creat and start daemons
    coordinatord_process = Process(target=coordinator.main, args=(logger_name, cord_to_builder_queue, cord_to_monitor_queue))

    processes.append(coordinatord_process)


    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.error("Keyboard interrupt in collector system.")
    finally:
        logger.info("Quit collector system. Bye!")
