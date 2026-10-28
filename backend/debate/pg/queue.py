from __future__ import annotations

import asyncio
import json
import re
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
        self._client = client

    @property
    def client(self) -> Any:
        """Created on first use, so importing the app (or running its tests) never needs AWS settings. The region is
        read from the queue URL (https://sqs.us-east-2.amazonaws.com/...), so no AWS_DEFAULT_REGION is needed either.
        Credentials are still needed when a message is actually sent (for example AWS_PROFILE=tangent)."""
        if self._client is None:
            import boto3

            m = re.match(r"https?://sqs\.([a-z0-9-]+)\.", self.queue_url)
            self._client = boto3.client("sqs", region_name=m.group(1) if m else None)
        return self._client

    async def enqueue(self, debate_id: str) -> None:
        await asyncio.to_thread(
            self.client.send_message,
            QueueUrl=self.queue_url,
            MessageBody=json.dumps({"debate_id": debate_id}),
            MessageGroupId=debate_id,
            MessageDeduplicationId=uuid.uuid4().hex,
        )
