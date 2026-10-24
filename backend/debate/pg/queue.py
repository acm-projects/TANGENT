from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional, Protocol


class Enqueuer(Protocol):
    async def enqueue(self, debate_id: str) -> None: ...


class SqsEnqueuer:
    """One FIFO message per run of a debate. The group id is the debate id, so a debate never runs twice at once.

    The message carries only the debate id. Answers and control signals live in the database (debates.resume_payload,
    debates.control), so nothing a user typed travels through the queue.
    """

    def __init__(self, queue_url: str, client: Optional[Any] = None) -> None:
        self.queue_url = queue_url
        if client is None:
            import boto3

            client = boto3.client("sqs")
        self.client = client

    async def enqueue(self, debate_id: str) -> None:
        await asyncio.to_thread(
            self.client.send_message,
            QueueUrl=self.queue_url,
            MessageBody=json.dumps({"debate_id": debate_id}),
            MessageGroupId=debate_id,
            MessageDeduplicationId=uuid.uuid4().hex,
        )
