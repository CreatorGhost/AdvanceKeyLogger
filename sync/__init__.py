"""
Offline-First Sync Engine with Conflict Resolution.

Provides durable, resumable, and bandwidth-adaptive synchronisation of
captured data to remote servers.  Works fully offline and syncs
automatically when connectivity is restored.

Components:
  * :class:`SyncLedger` — extended sync-state tracking per record
  * :class:`ConnectivityMonitor` — network detection, probing, policies
  * :class:`CheckpointManager` — resumable transfers with crash recovery
  * :class:`ConflictResolver` — pluggable conflict resolution strategies
  * :class:`SyncEngine` — orchestrator with priority queues, adaptive
    batching, compression, health metrics, and scheduling

Quick start::

    from sync import SyncEngine

    engine = SyncEngine(config, sqlite_store, transport)
    engine.start()           # starts connectivity monitor thread
    engine.process_pending() # call from main loop each cycle
    engine.stop()            # graceful shutdown
"""

from __future__ import annotations

from sync.ledger import SyncLedger, SyncState
from sync.connectivity import ConnectivityMonitor, NetworkType, ConnectionStatus
from sync.checkpoint import CheckpointManager, CheckpointState
from sync.conflict_resolver import ConflictResolver, ConflictStrategy
from sync.engine import SyncEngine, SyncEngineState, SyncHealth

__all__ = [
    "SyncLedger",
    "SyncState",
    "ConnectivityMonitor",
    "NetworkType",
    "ConnectionStatus",
    "CheckpointManager",
    "CheckpointState",
    "ConflictResolver",
    "ConflictStrategy",
    "SyncEngine",
    "SyncEngineState",
    "SyncHealth",
]
