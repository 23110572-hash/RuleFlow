"""Verification Kernel — the deterministic trust layer.

Agents PROPOSE; this kernel OWNS THE TRUTH. Every component here is
deterministic, side-effect-controlled, and independently unit-tested.
Nothing enters the compliance record without passing through the kernel.
"""

from app.kernel.citation import CitationResult, citation_fidelity, verify_citation
from app.kernel.coverage import CoverageCertificate, build_coverage_certificate, sweep_signals
from app.kernel.diff import DiffResult, ObligationChange, diff_obligations
from app.kernel.gaps import GapFinding, classify_gaps
from app.kernel.hashing import chain_hash, content_hash, sha256_hex
from app.kernel.obligation_tests import TestOutcome, compile_obligation, evaluate_test

__all__ = [
    "CitationResult",
    "citation_fidelity",
    "verify_citation",
    "CoverageCertificate",
    "build_coverage_certificate",
    "sweep_signals",
    "DiffResult",
    "ObligationChange",
    "diff_obligations",
    "GapFinding",
    "classify_gaps",
    "chain_hash",
    "content_hash",
    "sha256_hex",
    "TestOutcome",
    "compile_obligation",
    "evaluate_test",
]
