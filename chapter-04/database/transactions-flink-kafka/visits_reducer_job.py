#!/usr/bin/env python3
import datetime
import json
import os

from pyflink.common import SimpleStringSchema, WatermarkStrategy, Configuration, Duration, Types
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode, DataStream, \
    CheckpointingMode
from pyflink.datastream.connectors import DeliveryGuarantee
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer, KafkaSink, \
    KafkaRecordSerializationSchema

from visit_timestamp_assigner import VisitTimestampAssigner

# This configuration is very important
# Without it, you may encounter class loading-related errors, such as:
# Caused by: java.lang.ClassCastException: cannot assign instance of
#   org.apache.kafka.clients.consumer.OffsetResetStrategy to field
#   org.apache.flink.connector.kafka.source.enumerator.initializer.ReaderHandledOffsetsInitializer.offsetResetStrategy
#   of type org.apache.kafka.clients.consumer.OffsetResetStrategy
#   in instance of org.apache.flink.connector.kafka.source.enumerator.initializer.ReaderHandledOffsetsInitializer
config = Configuration()
config.set_string("classloader.resolve-order", "parent-first")
config.set_string("state.checkpoints.dir", "file:///tmp/dedp/ch04/flink-checkpoint")
env = StreamExecutionEnvironment.get_execution_environment(configuration=config)
env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
# The parallelism must be the same as the number of input partitions
# Otherwise the watermark won't advance
env.set_parallelism(1)
env.configure(config)
checkpoint_interval_30_seconds = 30000
env.enable_checkpointing(checkpoint_interval_30_seconds, mode=CheckpointingMode.EXACTLY_ONCE)
# Unlike PySpark, you have to define the JARs explicitly for Flink
env.add_jars(
    f"file://{os.getcwd()}/kafka-clients-3.2.3.jar",
    f"file://{os.getcwd()}/flink-connector-base-1.17.0.jar",
    f"file://{os.getcwd()}/flink-connector-kafka-1.17.0.jar"
)

kafka_source: KafkaSource = (KafkaSource.builder().set_bootstrap_servers('localhost:9094')
                             .set_group_id('visits_reader')
                             .set_starting_offsets(KafkaOffsetsInitializer.earliest())
                             .set_value_only_deserializer(SimpleStringSchema()).set_topics('visits').build())

watermark_strategy = WatermarkStrategy.for_bounded_out_of_orderness(Duration.of_seconds(5)) \
    .with_timestamp_assigner(VisitTimestampAssigner())

kafka_data_stream: DataStream = env.from_source(
    source=kafka_source,
    watermark_strategy=watermark_strategy,
    source_name="visits topics"
).uid("kafka-visits-reader").assign_timestamps_and_watermarks(watermark_strategy)


def map_json_to_reduced_visit(json_payload: str) -> str:
    event = json.loads(json_payload)
    event_time = int(datetime.datetime.fromisoformat(event['event_time']).timestamp())
    print(f'got event {event}')
    return json.dumps({'visit_id': event['visit_id'], 'event_time': event_time})


reduced_visits_jsons: DataStream = kafka_data_stream.map(map_json_to_reduced_visit, output_type=Types.STRING())

kafka_sink_valid_data: KafkaSink = (KafkaSink.builder().set_bootstrap_servers("localhost:9094")
                                    .set_record_serializer(KafkaRecordSerializationSchema.builder()
                                                           .set_topic('reduced_visits')
                                                           .set_value_serialization_schema(SimpleStringSchema())
                                                           .build())
                                    .set_delivery_guarantee(DeliveryGuarantee.EXACTLY_ONCE)
                                    .set_property('transaction.timeout.ms', str(1 * 60 * 1000))
                                    .build())

reduced_visits_jsons.sink_to(kafka_sink_valid_data)

env.execute('Transactional producer')
