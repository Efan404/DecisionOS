from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver


def get_checkpointer(db_path: str = "decisionos_checkpoints.db") -> SqliteSaver:
    """Return a SqliteSaver checkpoint instance.

    Note: SqliteSaver.from_conn_string returns a context-manager iterator.
    We enter it here and return the saver directly.  The caller is
    responsible for keeping it alive for the lifetime of the graph runner.
    """
    cm = SqliteSaver.from_conn_string(db_path)
    return cm.__enter__()
