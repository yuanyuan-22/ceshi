#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A minimal in-process async task runner using ThreadPoolExecutor.
This is a lightweight drop-in to start async tasks without requiring Celery/Django Q.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Dict

class SimpleTaskQueue:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    def enqueue(self, fn: Callable[..., Any], *args, **kwargs) -> str:
        fut = self._executor.submit(fn, *args, **kwargs)
        job_id = str(uuid.uuid4())
        with self._lock:
            self._futures[job_id] = fut
        return job_id

    def status(self, job_id: str) -> str:
        with self._lock:
            fut = self._futures.get(job_id)
        if fut is None:
            return "unknown"
        if fut.running():
            return "running"
        if fut.done():
            exc = fut.exception()
            return "failed" if exc else "done"
        return "queued"

    def result(self, job_id: str, timeout: float | None = None) -> Any:
        with self._lock:
            fut = self._futures.get(job_id)
        if fut is None:
            raise KeyError(job_id)
        return fut.result(timeout=timeout)

_DEFAULT_QUEUE = SimpleTaskQueue()

def enqueue_task(fn: Callable[..., Any], *args, **kwargs) -> str:
    return _DEFAULT_QUEUE.enqueue(fn, *args, **kwargs)

def task_status(job_id: str) -> str:
    return _DEFAULT_QUEUE.status(job_id)

def get_task_result(job_id: str, timeout: float | None = None) -> Any:
    return _DEFAULT_QUEUE.result(job_id, timeout=timeout)
