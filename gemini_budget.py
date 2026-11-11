"""Rate-limit actual Gemini API calls (not chat prompts). Handles 429 retry hints."""
from __future__ import annotations
import asyncio
import collections
import os
import random
import time
from typing import Callable

REPORT: Callable[[str],None] = lambda msg:None
TIMES=collections.deque()
LOCK=asyncio.Lock()
RATE=max(1,int(os.getenv('GEMINI_REQUESTS_PER_MINUTE','5')))

async def reserve():
    async with LOCK:
        while True:
            now=time.monotonic()
            while TIMES and now-TIMES[0]>=60:TIMES.popleft()
            if len(TIMES)<RATE:
                TIMES.append(now)
                return
            delay=max(.01,60-(now-TIMES[0]))
            REPORT(f'Gemini free-tier request pacing: {delay:.0f}s until next slot.')
            await asyncio.sleep(delay)

async def paced_invoke(model,messages):
    await reserve()
    return await model.ainvoke(messages)

def browser_model_class(cls):
    return cls
