import asyncio
import json
from typing import Any, Awaitable, Callable, Optional

import aio_pika
from aio_pika import ExchangeType, IncomingMessage, Message
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from agent_shared.config import settings
from agent_shared.messages import (
    EXCHANGE_DLX,
    EXCHANGE_MAIN,
    QUEUE_DLQ,
    QUEUE_FLASHCARD,
    QUEUE_PROGRESS,
    QUEUE_QUIZ,
    QUEUE_QUIZ_SUBMIT,
    QUEUE_RESPONSES,
    QUEUE_STUDY,
)

WORK_QUEUES = [
    QUEUE_STUDY,
    QUEUE_QUIZ,
    QUEUE_QUIZ_SUBMIT,
    QUEUE_PROGRESS,
    QUEUE_FLASHCARD,
    QUEUE_RESPONSES,
]

QUEUE_ARGS = {
    "x-dead-letter-exchange": EXCHANGE_DLX,
    "x-dead-letter-routing-key": QUEUE_DLQ,
}


async def connect_rabbit() -> AbstractRobustConnection:
    return await aio_pika.connect_robust(settings.rabbitmq_url)


async def declare_work_queue(channel: AbstractChannel, queue_name: str):
    return await channel.declare_queue(
        queue_name,
        durable=True,
        arguments=QUEUE_ARGS,
    )


async def setup_topology(channel: AbstractChannel) -> None:
    exchange = await channel.declare_exchange(EXCHANGE_MAIN, ExchangeType.DIRECT, durable=True)
    dlx = await channel.declare_exchange(EXCHANGE_DLX, ExchangeType.DIRECT, durable=True)

    dlq = await channel.declare_queue(QUEUE_DLQ, durable=True)
    await dlq.bind(dlx, routing_key=QUEUE_DLQ)

    for qname in WORK_QUEUES:
        queue = await declare_work_queue(channel, qname)
        await queue.bind(exchange, routing_key=qname)

    return None


async def publish_json(
    channel: AbstractChannel,
    routing_key: str,
    payload: dict[str, Any],
    headers: Optional[dict] = None,
) -> None:
    exchange = await channel.get_exchange(EXCHANGE_MAIN)
    body = json.dumps(payload, default=str).encode()
    msg = Message(
        body=body,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
        headers=headers or {},
    )
    await exchange.publish(msg, routing_key=routing_key)


def _retry_count(message: IncomingMessage) -> int:
    headers = message.headers or {}
    return int(headers.get("x-retry-count", 0))


async def consume_with_retry(
    channel: AbstractChannel,
    queue_name: str,
    handler: Callable[[dict], Awaitable[None]],
    max_retries: int = 3,
) -> None:
    queue = await declare_work_queue(channel, queue_name)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=False):
                try:
                    data = json.loads(message.body.decode())
                    await handler(data)
                except Exception:
                    retries = _retry_count(message)
                    if retries < max_retries:
                        # exponential backoff: 1s, 2s, 4s — RabbitMQ doesn't sleep for us
                        await asyncio.sleep(2**retries)
                        await publish_json(
                            channel,
                            queue_name,
                            json.loads(message.body.decode()),
                            headers={"x-retry-count": retries + 1},
                        )
                    else:
                        dlx = await channel.get_exchange(EXCHANGE_DLX)
                        await dlx.publish(
                            Message(
                                body=message.body,
                                headers={**(message.headers or {}), "x-retry-count": retries},
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            ),
                            routing_key=QUEUE_DLQ,
                        )
                    raise


async def queue_depth(channel: AbstractChannel, queue_name: str) -> int:
    queue = await channel.declare_queue(queue_name, durable=True, passive=True)
    return queue.declaration_result.message_count or 0
