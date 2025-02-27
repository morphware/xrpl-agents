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
    TEST_TOPIC = Config.KAFKA_OUT_TOPIC         # For standard messages
    
    # Create Kafka producer for standard messages
    producer = create_kafka_producer(BOOTSTRAP_SERVERS)
    consumer = create_kafka_consumer(BOOTSTRAP_SERVERS, "chat-ui")
    consumer = consume_from_kafka(consumer, TEST_TOPIC)
    consume_timestamp = time.time() * 1000
    
    while True:
        try:
            # Poll for messages without waiting for user input
            message, key = get_kafka_latest_message(consumer, timestamp=consume_timestamp)
            print(message)
                
            # Small sleep to prevent CPU overload
            time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("Stopping consumer...")
            break
        except Exception as e:
            print(f"Error receiving message: {str(e)}")
            
    producer.close()
    consumer.close()

if __name__ == "__main__":
    main()