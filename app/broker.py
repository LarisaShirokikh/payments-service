from faststream.rabbit import RabbitBroker, RabbitQueue

from app.config import settings

broker = RabbitBroker(settings.rabbitmq_url)

# main work queue; failed messages dead-letter (via the default exchange) to payments.dlq
NEW_QUEUE = RabbitQueue(
    "payments.new",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "payments.dlq",
    },
)
DLQ = RabbitQueue("payments.dlq", durable=True)


async def declare_topology() -> None:
    await broker.declare_queue(NEW_QUEUE)
    await broker.declare_queue(DLQ)


async def publish_new_payment(payload: dict) -> None:
    await broker.publish(payload, queue=NEW_QUEUE)


async def publish_to_dlq(payload: dict) -> None:
    await broker.publish(payload, queue=DLQ)
