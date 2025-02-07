from kafka import KafkaProducer, KafkaConsumer
import json

def create_kafka_producer(bootstrap_servers) -> KafkaProducer:
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer

def create_kafka_consumer(bootstrap_servers, group_id, offset='latest') -> KafkaConsumer:
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset=offset,
        enable_auto_commit=True,
        group_id=group_id    )
    return consumer

def send_to_kafka(producer, topic, message):
    producer.send(topic, message)
    producer.flush()

def consume_from_kafka(consumer, topic):
    consumer.subscribe(topics=[topic])
    return consumer

def get_kafka_messages(consumer):
    messages = consumer.poll(timeout_ms=1000)
    return messages