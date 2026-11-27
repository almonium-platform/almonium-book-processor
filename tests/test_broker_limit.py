"""A job waiting for its retry time must not take the worker's one place.

Celery holds a job with a countdown in the worker until it is due and raises its limit
at the broker by one for each, so the next job still arrives. It can only raise a
channel-wide limit: one set per consumer is fixed once the consumer exists. kombu 5.7.0
began asking RabbitMQ 4 for the per-consumer kind, and on the deployed 4.1 broker a
download retrying a library that was down held every job behind it for minutes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from kombu.transport import pyamqp


@pytest.mark.parametrize("version", ["3.13.7", "4.1.0", "4.1.8"])
def test_the_worker_asks_rabbitmq_for_a_limit_it_can_raise(version: str) -> None:
    connection = SimpleNamespace(server_properties={"product": "RabbitMQ", "version": version})

    # False is "this broker's limits are not the specification's": Celery then sets the
    # channel-wide one, the only kind it can raise while it holds waiting jobs
    assert pyamqp.Transport.qos_semantics_matches_spec(None, connection) is False
