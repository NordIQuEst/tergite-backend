"""Utilities for testing rq workers and queues"""
from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty


class WindowsSimpleWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty
