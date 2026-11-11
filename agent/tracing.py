"""LangSmith with PII masking (E4): emails, phones and payment details are masked before any trace leaves the process."""
import contextlib, os
from agent.safety import mask_obj


@contextlib.contextmanager
def traced():
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        yield
        return
    from langsmith import Client, tracing_context
    client = Client(hide_inputs=mask_obj, hide_outputs=mask_obj)
    with tracing_context(client=client, enabled=True, project_name=os.getenv("LANGSMITH_PROJECT", "gigbid")):
        yield
