"""Mode-agnostic failover suite core for the central database engines.

The core holds the write-continuity checker output model, the audit, the
targets and the scenario list. Lab bring-up, checker configuration and fault
injection live in per-mode adapters (``utils.failover.swarm``).
"""
