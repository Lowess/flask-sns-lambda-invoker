import atexit
import json
import logging
import os
import signal
import sys
import threading
import time
from logging.config import dictConfig
from os import environ
from os.path import abspath, dirname, join
from xml.etree import ElementTree

import boto3
import botocore
import requests
from flask import Flask, current_app, request, url_for


def get_callable_handler_function(src, handler):
    """Translate a string of the form "module.function" into a callable
    function.
    :param str src:
      The path to your Lambda project containing a valid handler file.
    :param str handler:
      A dot delimited string representing the `<module>.<function name>`.
    """

    def load_source(module_name, module_path):
        """Loads a python module from the path of the corresponding file."""

        if sys.version_info[0] == 3 and sys.version_info[1] >= 5:
            import importlib.util

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        elif sys.version_info[0] == 3 and sys.version_info[1] < 5:
            import importlib.machinery

            loader = importlib.machinery.SourceFileLoader(module_name, module_path)
            module = loader.load_module()
        return module

    # "cd" into `src` directory.
    os.chdir(src)

    module_name, function_name = handler.split(".")
    filename = f"{handler.split('.')[0]}.py"

    path_to_module_file = join(src, filename)
    module = load_source(module_name, path_to_module_file)
    return getattr(module, function_name)


def get_ngrok_endpoint(endpoint):
    return requests.get(f"{endpoint}/api/tunnels/command_line").json()["public_url"]


def default_lambda_handler(event, context):
    print(f"context={context} event={event}")


def configure_app(app):
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
                },
                "colored": {
                    "()": "colorlog.ColoredFormatter",
                    "format": (
                        "%(cyan)s%(asctime)s,%(msecs)03d%(reset)s %(bold_yellow)s %(levelname)8s%(reset)s "
                        "%(purple)s%(filename)s:%(lineno)d%(reset)s - %(message_log_color)s%(message)s"
                    ),
                    "log_colors": {
                        "DEBUG": "green",
                        "INFO": "white",
                        "WARNING": "yellow",
                        "ERROR": "red",
                        "CRITICAL": "red,bg_white",
                    },
                    "secondary_log_colors": {
                        "message": {
                            "DEBUG": "green",
                            "INFO": "white",
                            "WARNING": "yellow",
                            "ERROR": "red",
                            "CRITICAL": "red,bg_white",
                        }
                    },
                },
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "colored",
                }
            },
            "root": {"level": "INFO", "handlers": ["wsgi"]},
        }
    )

    app.config["SNS_TOPIC_ARN"] = environ.get("SNS_TOPIC_ARN")
    app.config["LAMBDA_SRC"] = environ.get("LAMBDA_SRC", dirname(abspath(__file__)))
    app.config["LAMBDA_HANDLER"] = environ.get(
        "LAMBDA_HANDLER", "app.default_lambda_handler"
    )
    app.config["NGROK_ENDPOINT"] = environ.get(
        "NGROK_ENDPOINT", "http://host.docker.internal:4040"
    )

    try:
        app.config["NGROK_PUBLIC_URL"] = get_ngrok_endpoint(
            app.config["NGROK_ENDPOINT"]
        )
        app.logger.info(f"Ngrok Public endpoint is: {app.config['NGROK_PUBLIC_URL']}")
    except requests.exceptions.ConnectionError:
        app.logger.error(f"Failed to query Ngrok on {app.config['NGROK_ENDPOINT']}")
        sys.exit(1)

    # Show app settings
    app.logger.info(f"Flask app initialized with SNS {app.config['SNS_TOPIC_ARN']}")
    app.logger.info(f"Flask app lambda handler set to '{app.config['LAMBDA_HANDLER']}'")


def subscribe(app, client, sns_topic_arn, sns_endpoint):
    # Subscribe to SNS topic
    app.logger.info("Flask app subscribe thread started...")

    with app.app_context():
        try:
            while requests.get(url_for("status")).raise_for_status():
                pass
        except RuntimeError:
            pass

    try:
        app.logger.info(f"Subscribing to {sns_topic_arn}")
        response = client.subscribe(
            TopicArn=sns_topic_arn,
            Protocol="https",
            Endpoint=sns_endpoint,
            ReturnSubscriptionArn=True,
        )
        app.logger.info(f"Subscribed successfully to {sns_topic_arn}")

    except botocore.exceptions.ParamValidationError as e:
        app.logger.error(f"The provided Topic ARN ({sns_topic_arn}) is invalid...")
        sys.exit(1)


def create_app(config_filename):
    app = Flask(__name__)

    configure_app(app)

    client = boto3.client("sns")

    # SNS subscribe thread
    subscribe_thread = threading.Thread(
        target=subscribe,
        kwargs={
            "app": app,
            "client": client,
            "sns_topic_arn": app.config["SNS_TOPIC_ARN"],
            "sns_endpoint": app.config["NGROK_PUBLIC_URL"],
        },
    )
    subscribe_thread.start()

    def shutdown(thread, arn):
        if thread:
            thread.join()
            client.unsubscribe(SubscriptionArn=arn)
            app.logger.info(f"Successfully removed subscription {arn} from topic !")

    def router(data):
        payload = json.loads(request.data)

        # Handle SNS subscription confirmation
        if payload.get("Type", None) == "SubscriptionConfirmation":
            app.logger.info(f"{payload['Message']}")

            subscription = requests.get(payload["SubscribeURL"]).text
            # Parse XML Document to extract SubscriptionArn
            tree = ElementTree.fromstring(subscription)

            unsubscribe_arn = next(
                elem.text
                for elem in tree.iter()
                if app.config["SNS_TOPIC_ARN"] in elem.text
            )

            # Configure a callback to run on exit
            atexit.register(shutdown, thread=subscribe_thread, arn=unsubscribe_arn)

            msg = f"Automatically subscribed to topic, unsubscribe callback configured with {unsubscribe_arn}"
            app.logger.info(msg)
            return msg

        # Handle SNS Notification to call the lambda function
        elif payload.get("Type", None) == "Notification":
            fn = get_callable_handler_function(
                src=app.config["LAMBDA_SRC"], handler=app.config["LAMBDA_HANDLER"]
            )
            event = {
                "Records": [
                    {
                        "EventSource": "aws:sns",
                        "EventVersion": "1.0",
                        "EventSubscriptionArn": "",
                        "Sns": payload,
                    }
                ]
            }
            app.logger.info(f"Firing up Lambda with event: {event}")
            fn(
                event=event,
                context={},
            )
            return f"Lambda successfully invoked with: {event}"
        else:
            msg = f"Don't know how to handle {payload}"
            app.logger.error(msg)
            return msg

    @app.route("/status", methods=["GET"])
    def status():
        return "Healthy"

    @app.route("/", methods=["GET", "POST"])
    def handler():
        return router(request.data)

    return app
