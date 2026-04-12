"""Summarization pipeline — disabled.

The original pipeline ran background LLM calls every 30s across 6 levels
(5min→10min→30min→1hr→12hr→daily), which was too heavy for a laptop.

Replaced with a no-op stub. The system now only keeps the raw event log
for the last 5 minutes — no background threads, no extra LLM calls.
"""

from src.configs.logging_config import get_logger

logger = get_logger(__name__)


class SummarizationPipeline:
    def start(self):
        logger.info("SummarizationPipeline: disabled (5-min only mode)")

    def stop(self):
        pass

    def register_thread(self, thread_id: str):
        pass


_pipeline = SummarizationPipeline()


def get_pipeline() -> SummarizationPipeline:
    return _pipeline
