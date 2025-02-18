import logging
import sys, json, time
from kafka import KafkaProducer, KafkaConsumer
import requests
from config import Config
from pydantic import BaseModel, ConfigDict
from typing import Optional, Union
import uuid


class APIHandler(logging.Handler):
    def __init__(self, api_endpoint, api_key, chat_uuid):
        logging.Handler.__init__(self)
        self.api_key = api_key
        self.chat_uuid = chat_uuid
        self.api_endpoint = api_endpoint + self.chat_uuid

    def emit(self, messages):
        try:
            input_message, response_message = messages.msg
            payload, headers = create_chats_message_payload(input_message, response_message, self.chat_uuid, self.api_endpoint, api_key=self.api_key)
            requests.post(self.api_endpoint, data=json.dumps(payload), headers=headers)
        except Exception:
            self.handleError(response_message)

class KafkaHandler(logging.Handler):
    def __init__(self, producer, topic):
        logging.Handler.__init__(self)
        self.producer = producer
        self.topic = topic

    def emit(self, record):
        try:
            msg = self.format(record)
            self.producer.send(self.topic, msg)
        except Exception:
            self.handleError(record)

def setup_logger(name: str, log_file: str = None, kafka_producer=None, kafka_topic=None) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Kafka handler if specified
    if kafka_producer and kafka_topic:
        kafka_handler = KafkaHandler(kafka_producer, kafka_topic)
        kafka_handler.setFormatter(formatter)
        logger.addHandler(kafka_handler)
    
    return logger

def setup_kafka_logger(name: str, kafka_producer=None, kafka_topic=None) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(message)s'
    )
    # Kafka handler if specified
    if kafka_producer and kafka_topic:
        kafka_handler = KafkaHandler(kafka_producer, kafka_topic)
        kafka_handler.setFormatter(formatter)
        logger.addHandler(kafka_handler)
    
    return logger

def chat_ui_logger(name: str, api_endpoint: str, api_key: str, chat_uuid: str) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(message)s'
    )
    api_handler = APIHandler(api_endpoint, api_key, chat_uuid)
    api_handler.setFormatter(formatter)
    logger.addHandler(api_handler)
    
    return logger

def setup_debug_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    logging.getLogger('src.agent.agent').setLevel(logging.DEBUG)

    agent_handler = logging.FileHandler('agent_output.log')
    agent_handler.setLevel(logging.DEBUG)
    agent_format = logging.Formatter('%(asctime)s - AGENT OUTPUT:\n%(message)s\n')
    agent_handler.setFormatter(agent_format)
    logger.addHandler(agent_handler)
    
    return logger