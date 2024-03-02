import time
from typing import Optional

from confluent_kafka import Producer


class KafkaWriterIndividualSend:

    def __init__(self, bootstrap_server: str, output_topic: str):
        self.producer: Optional[Producer] = None
        self.partition_id: Optional[int] = None
        self.output_topic = output_topic
        self.bootstrap_server = bootstrap_server

    def open(self, partition_id, epoch_id):
        self.partition_id = partition_id
        self.producer = Producer({
            'bootstrap.servers': self.bootstrap_server,
            'max.in.flight.requests.per.connection': 1,

        })
        return True

    def process(self, row):
        print(f'[{self.partition_id}] Sending {row.value}')
        self.producer.produce(
            topic=self.output_topic, key=row.key, value=row.value
        )
        self.producer.flush()
        # adding this sleep to see better "individual" delivery
        time.sleep(2)

    def close(self, error):
        pass
