"""In-memory telemetry and latency diagnostics for Hyprash Phase 6.

Tracks the full command lifecycle using monotonic clocks (monotonic_ns) to measure:
- ptt_to_transcript_ms (Voxtype)
- nlu_normalize_ms (Rule layer)
- laya_inference_ms (0 ms if bypassed by deterministic rule)
- plan_validation_ms
- execution_act_ms
- verification_ms
- total_e2e_ms
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import statistics
import time
from typing import Any
import uuid

MAX_HISTORY = 100
_HISTORY: list[dict[str, Any]] = []


@dataclass
class StageTimer:
    start_ns: int = field(default_factory=time.monotonic_ns)
    timings: dict[str, float] = field(default_factory=lambda: {
        'ptt_to_transcript_ms': 0.0,
        'nlu_normalize_ms': 0.0,
        'laya_inference_ms': 0.0,
        'plan_validation_ms': 0.0,
        'execution_act_ms': 0.0,
        'verification_ms': 0.0,
        'total_e2e_ms': 0.0,
    })

    def record_stage(self, stage_name: str, duration_ms: float):
        self.timings[stage_name] = round(duration_ms, 2)

    @contextmanager
    def measure(self, stage_name: str):
        t0 = time.monotonic_ns()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000.0
            self.timings[stage_name] = round(elapsed_ms, 2)

    def finish(self) -> dict[str, float]:
        total_ms = (time.monotonic_ns() - self.start_ns) / 1_000_000.0
        self.timings['total_e2e_ms'] = round(total_ms, 2)
        return dict(self.timings)


def record_trace(
    raw_transcript: str,
    normalized_text: str,
    resolution_source: str,  # 'rule' | 'laya'
    resolved_intent: str,
    confidence: float,
    plan_steps: list[str],
    outcome: str,  # 'succeeded' | 'failed' | 'cancelled' | 'clarifying'
    latencies_ms: dict[str, float],
    entities: dict[str, Any] | None = None,
    ambiguity_reason: str = "",
    error: str = "",
) -> dict[str, Any]:
    trace = {
        'id': uuid.uuid4().hex[:8],
        'timestamp': time.time(),
        'raw_transcript': raw_transcript,
        'normalized_text': normalized_text,
        'resolution_source': resolution_source,
        'resolved_intent': resolved_intent,
        'confidence': confidence,
        'entities': entities or {},
        'plan_steps': plan_steps,
        'outcome': outcome,
        'ambiguity_reason': ambiguity_reason,
        'error': error,
        'latencies_ms': latencies_ms,
    }
    _HISTORY.append(trace)
    if len(_HISTORY) > MAX_HISTORY:
        _HISTORY.pop(0)
    return trace


def get_recent_traces(count: int = 10) -> list[dict[str, Any]]:
    return list(_HISTORY[-count:])


def clear_traces():
    _HISTORY.clear()


def get_diagnostics_summary() -> dict[str, Any]:
    if not _HISTORY:
        return {'sample_count': 0, 'message': 'No commands recorded yet.'}

    totals = [t['latencies_ms'].get('total_e2e_ms', 0.0) for t in _HISTORY]
    rule_traces = [t for t in _HISTORY if t.get('resolution_source') == 'rule']
    laya_traces = [t for t in _HISTORY if t.get('resolution_source') == 'laya']

    def calc_stats(data: list[float]) -> dict[str, float]:
        if not data:
            return {'count': 0, 'median': 0.0, 'p95': 0.0, 'min': 0.0, 'max': 0.0}
        sorted_d = sorted(data)
        count = len(sorted_d)
        p95_idx = max(0, int(count * 0.95) - 1)
        return {
            'count': count,
            'median': round(statistics.median(sorted_d), 2),
            'p95': round(sorted_d[p95_idx], 2),
            'min': round(sorted_d[0], 2),
            'max': round(sorted_d[-1], 2),
        }

    stages = [
        'ptt_to_transcript_ms',
        'nlu_normalize_ms',
        'laya_inference_ms',
        'plan_validation_ms',
        'execution_act_ms',
        'verification_ms',
        'total_e2e_ms',
    ]
    stage_stats = {
        s: calc_stats([t['latencies_ms'].get(s, 0.0) for t in _HISTORY if s in t['latencies_ms']])
        for s in stages
    }

    outcomes = {}
    for t in _HISTORY:
        outcomes[t['outcome']] = outcomes.get(t['outcome'], 0) + 1

    rule_totals = [t['latencies_ms'].get('total_e2e_ms', 0.0) for t in rule_traces]
    laya_totals = [t['latencies_ms'].get('total_e2e_ms', 0.0) for t in laya_traces]

    return {
        'sample_count': len(_HISTORY),
        'outcomes': outcomes,
        'cold_start_total_ms': totals[0] if totals else 0.0,
        'warm_median_ms': round(statistics.median(totals[1:]), 2) if len(totals) > 1 else (totals[0] if totals else 0.0),
        'stages': stage_stats,
        'rule_path': {
            'count': len(rule_traces),
            'stats': calc_stats(rule_totals),
        },
        'laya_path': {
            'count': len(laya_traces),
            'stats': calc_stats(laya_totals),
        },
    }
