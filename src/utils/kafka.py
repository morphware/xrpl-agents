from kafka import KafkaProducer, KafkaConsumer
import json
import time

def forgiving_json_deserializer(v):
    if v is None:
        return None
    try:
        return json.loads(v.decode('utf-8'))
    except json.decoder.JSONDecodeError:
        print('Unable to decode: %s', v)
        return None

def create_kafka_producer(bootstrap_servers) -> KafkaProducer:
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        key_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer

def create_kafka_consumer(bootstrap_servers, group_id, offset='latest') -> KafkaConsumer:
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset='latest',
        enable_auto_commit=True,
        group_id=group_id,
        consumer_timeout_ms=1000,
        value_deserializer=forgiving_json_deserializer,
        key_deserializer=forgiving_json_deserializer
        )
    consumer.poll(timeout_ms=0)
    return consumer

def send_to_kafka(producer, topic, message, key=None):
    if producer:
        if key:
            producer.send(topic, key=key, value=message)
        else:
            producer.send(topic, message)
        producer.flush()

def consume_from_kafka(consumer, topic):
    consumer.subscribe(topics=[topic])
    return consumer

def get_kafka_messages(consumer):
    messages = consumer.poll(timeout_ms=0)
    return messages

def get_kafka_latest_message(kafka_in, timestamp=time.time()*1000, message_id=None):
    # for msg in kafka_in:
    #     print (msg)
    waiting = True
    key=None
    while waiting:
        message = get_kafka_messages(kafka_in)
        if not message:
            continue
        else:
            for topic_partition, records in message.items():
                for record in records:
                    try:
                        
                        if record.timestamp > timestamp:
                            if message_id:
                                if record.key == message_id:
                                    key = record.key
                                    waiting = False
                                    break
                            else:
                                key = record.key
                                waiting = False
                                break
                    except Exception as e:
                        print(f"Error processing message: {str(e)}")
    try:
        response = str(record.value)
        print("Received message: " + response)
        return response, key
    except Exception as e:
        response = f"Error processing message: {str(e)}"
        return response, key