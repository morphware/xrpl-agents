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
    OUT_TOPIC = Config.KAFKA_OUT_TOPIC
    
    # Create Kafka producer for standard messages
    producer = create_kafka_producer(BOOTSTRAP_SERVERS)
    consumer = create_kafka_consumer(BOOTSTRAP_SERVERS, "backend")
    consumer = consume_from_kafka(consumer, TEST_TOPIC + "_OUT")
    consume_timestamp = time.time() * 1000
    message_id = str(uuid.uuid4())
    
    # Standard test messages
    test_messages = [
        {'Account': 'rGzqrf37zwToSw4JyHdFKNaA1E1sKNmUHS',
            'TransactionType': 'Payment',
            'Flags': 0,
            'SigningPubKey': '',
            'Amount': '100000',
            'Destination': 'raaFKKmgf6CRZttTVABeTcsqzRQ51bNR6Q'
        },
        {'Account': 'raaFKKmgf6CRZttTVABeTcsqzRQ51bNR6Q',
            'TransactionType': 'Payment',
            'Flags': 0,
            'SigningPubKey': '',
            'Amount': '100000',
            'Destination': 'rGzqrf37zwToSw4JyHdFKNaA1E1sKNmUHS'
        },
        {'Account': 'rGzqrf37zwToSw4JyHdFKNaA1E1sKNmUHS',
            'TransactionType': 'Payment',
            'Flags': 0,
            'SigningPubKey': '',
            'Amount': '100000',
            'Destination': 'raaFKKmgf6CRZttTVABeTcsqzRQ51bNR6Q'
        }
    ]
    
    # Send standard test messages
    try:
        for message in test_messages:
            send_to_kafka(producer, TEST_TOPIC + "_IN", message, key=message_id)
            print(f"Sent message: {message}")
            # Allow some time for threads to process messages
            response, key = get_kafka_latest_message(consumer, timestamp=consume_timestamp, message_id=message_id)
            print(f"Received message: {response} with key: {key}")
            send_to_kafka(producer, OUT_TOPIC, response, key=key)
            print(f"Sent response: {response}")
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        

    producer.close()
    consumer.close()

if __name__ == "__main__":
    main()