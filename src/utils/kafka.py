from kafka import KafkaProducer, KafkaConsumer
import json
import time

def create_kafka_producer(bootstrap_servers) -> KafkaProducer:
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer

def create_kafka_consumer(bootstrap_servers, group_id, offset='latest') -> KafkaConsumer:
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id=group_id,
        consumer_timeout_ms=1000
    )
    consumer.poll(timeout_ms=0)
    return consumer

def send_to_kafka(producer, topic, message):
    producer.send(topic, message)
    producer.flush()

def consume_from_kafka(consumer, topic):
    consumer.subscribe(topics=[topic])
    return consumer

def get_kafka_messages(consumer):
    messages = consumer.poll(timeout_ms=0)
    return messages

def get_kafka_latest_message(kafka_in):
    for msg in kafka_in:
        print (msg)
    waiting = True
    timestamp=time.time()*1000
    while waiting:
        message = get_kafka_messages(kafka_in)
        if not message:
            continue
        else:
            for topic_partition, records in message.items():
                for record in records:
                    if record.timestamp > timestamp:
                        message = record
                        waiting = False
                        break
    try:
        response = str(message.value.decode('utf-8'))
        print("Received message: " + response)
        return response
    except Exception as e:
        response = f"Error processing message: {str(e)}"
        return e