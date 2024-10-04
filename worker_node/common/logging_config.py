import logging
import logging.config
from colorlog import ColoredFormatter

# Centralized configuration for color scheme and formats
LOG_COLORS = {
    'DEBUG': 'cyan',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}
COLORED_FORMAT = "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Logging configuration dictionary
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'colored': {
            '()': ColoredFormatter,
            'format': COLORED_FORMAT,
            'datefmt': DATE_FORMAT,
            'log_colors': LOG_COLORS,
        },
        'standard': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
            'datefmt': DATE_FORMAT,
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'colored',
        },
    },
    'loggers': {
        # Automatically create loggers for common modules
        **{
            logger_name: {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False,
            } for logger_name in ('builderd', 'monitord', 'coordinatord')
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console'],
    },
}

# Apply logging configuration
logging.config.dictConfig(LOGGING)
