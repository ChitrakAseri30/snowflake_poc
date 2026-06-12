import logging
import os
import sys

from datetime import datetime
from logging.handlers import RotatingFileHandler

## Module level constants which can be changed based on needs
# Flag to enable console log handler. Can be True or False
CONSOLE_HANDLER_ENABLED = True
# Flag to enable file log handler. Can be True or False
FILE_HANDLER_ENABLED = False
# Setting logging level. Can be logging.INFO or logging.WARN or logging.DEBUG
LOG_LEVEL = logging.DEBUG
# Default log file directory and name
FILE_HANDLER_LOG_DIR = os.path.dirname(os.path.realpath(__file__)) + os.sep + "logs"
FILE_HANDLER_LOG_NAME = "DLPLogSetup.log"
# Default maximum log file size
FILE_HANDLER_MAX_FILE_SIZE = 10 * 1024 * 1024
# Default log formatter. Made similar to Airflow log formatter
LOG_FORMATTER_KEY = "[%(asctime)s] {%(filename)s:%(lineno)s} %(levelname)-5.5s - %(message)s"


def set_log_level(logger_object, log_level):
    """
    Purpose   :   Setting the logger level to DEBUG/INFO/WARN/ERROR
    Input     :   Logger object and logger level
    Output    :   None
    """
    if log_level is None:
        logger_object.setLevel(LOG_LEVEL)
    elif log_level.lower() == "debug":
        logger_object.setLevel(logging.DEBUG)
    elif log_level.lower() == "info":
        logger_object.setLevel(logging.INFO)
    elif log_level.lower() == "warning":
        logger_object.setLevel(logging.WARNING)
    elif log_level.lower() == "error":
        logger_object.setLevel(logging.ERROR)
    else:
        logger_object.setLevel(LOG_LEVEL)


def get_logger(log_level=None, enable_console_log=CONSOLE_HANDLER_ENABLED, enable_file_log=FILE_HANDLER_ENABLED,
               file_log_dir=FILE_HANDLER_LOG_DIR, file_log_name=FILE_HANDLER_LOG_NAME):
    """
    Purpose   :   If no existing log handler is found it creates new log handlers (console and file handlers supported
                  for now). It then sets the logging level of the handler to INFO/WARN/DEBUG
    Input     :   Optional log level - DEBUG/INFO/WARNING/ERROR, Optional flag to enable console logging - True/False
                  Optional flag to enable file logging - True/False, Optional file log directory path
                  Optional log file name
    Output    :   Logger object with log handlers
    """
    # Get existing logger object
    root_logger = logging.getLogger()
    # Set log level for the logger
    set_log_level(root_logger, log_level)

    # Check whether the logger object has any existing handlers
    if not root_logger.handlers:
        log_formatter = logging.Formatter(LOG_FORMATTER_KEY)

        # Add console handler
        if enable_console_log:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(log_formatter)
            root_logger.addHandler(console_handler)

        # Add file handler
        if enable_file_log:
            try:
                log_file_path = os.path.join(file_log_dir, file_log_name)
                if not os.path.exists(os.path.dirname(log_file_path)):
                    os.makedirs(os.path.dirname(log_file_path))
                file_handler = RotatingFileHandler(log_file_path, mode="a",
                                                   maxBytes=FILE_HANDLER_MAX_FILE_SIZE, delay=True)
                file_handler.setFormatter(log_formatter)
                root_logger.addHandler(file_handler)

            except Exception as ex:
                sys.stderr.write("Error while setting file handler. ERROR - " + str(ex) + "\n")

    return root_logger