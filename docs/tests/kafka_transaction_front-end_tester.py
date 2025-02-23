import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.utils.kafka import create_kafka_producer, create_kafka_consumer, send_to_kafka, consume_from_kafka, get_kafka_messages, get_kafka_latest_message
import json
import time
from threading import Thread
from src.config import Config
import uuid

def main():
    # Kafka configuration
    BOOTSTRAP_SERVERS = Config.KAFKA_BOOTSTRAP_SERVERS  # Replace with your Kafka server
    TEST_TOPIC = Config.KAFKA_TX_TOPIC         # For standard messages
    
    # Create Kafka producer for standard messages
    producer = create_kafka_producer(BOOTSTRAP_SERVERS)
    consumer = create_kafka_consumer(BOOTSTRAP_SERVERS, "chat-ui")
    consumer = consume_from_kafka(consumer, TEST_TOPIC + "_IN")
    consume_timestamp = time.time() * 1000
    
    while True:
        # Allow some time for threads to process messages
        response, key = get_kafka_latest_message(consumer, timestamp=consume_timestamp)
        message_id = key
        print(f"Received message: {response}")
        user_message = input(f"Enter message to send for transaction {message_id}, (or type 'quit' to exit): ")
        if user_message.lower() == 'quit':
            break
        try:
            send_to_kafka(producer, TEST_TOPIC + "_OUT", user_message, key=message_id)
            print(f"Sent message: {user_message}")
        except Exception as e:
            print(f"Error sending message: {str(e)}")
            
    producer.close()
    consumer.close()

if __name__ == "__main__":
    main()