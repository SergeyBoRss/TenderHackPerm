import logging
import logging.config


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": "INFO",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": "INFO",
            },
            "loggers": {
                "app": {
                    "handlers": ["default"],
                    "level": "INFO",
                    "propagate": False,
                }
            },
        }
    )
