# Independent Report Card dead-man monitor contract

The monitor must run on infrastructure independent of GitHub Actions and read a
heartbeat record containing a unique run ID, monotonic non-negative sequence,
start time, completion time and terminal status. GitHub notification state is
not an accepted heartbeat source.

For each expected run, the monitor evaluates never-started, over-grace running,
failed-terminal and healthy states. Alert envelopes have deterministic event
IDs derived from run ID, sequence, state and independent source, allowing an
adapter to deduplicate retries. An adapter must pass a destination healthcheck
and return a non-empty delivery confirmation. Otherwise monitoring fails
closed and unattended activation remains prohibited.

The repository provides the protocol, evaluator and CLI artifact generation.
It does not install a monitor, select a communication channel, store channel
credentials or send an alert. Those require the owner's chosen destination and
a separately tested external host.
