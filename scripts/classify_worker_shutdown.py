"""Classify supplied read-only host evidence; never infer OOM from cancellation."""
import re

def classify(text):
    oom = bool(re.search(r'Out of memory: Killed process|oom-kill:|Memory cgroup out of memory', text, re.I))
    shutdown = 'runner has received a shutdown signal' in text.lower()
    return {'oom_evidence_present': oom, 'runner_shutdown_signal_present': shutdown,
            'cause': 'HOST_OOM_RECORDED' if oom else 'SHUTDOWN_INITIATOR_UNPROVEN' if shutdown else 'INSUFFICIENT_EVIDENCE'}
