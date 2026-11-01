"""Test suite for Flagship Agent Features:
1. Live Action Timeline event streaming
2. Human-in-the-Loop (HITL) approval prompt & escalation
3. Routine auto-recording & immediate execution
"""
import unittest
from tests.test_simular_features import SimularFeaturesTests


class AgentFeaturesTests(SimularFeaturesTests):
    """Inherits full test suite for Action Timeline, HITL, and Routine Recording."""
    pass


if __name__ == "__main__":
    unittest.main()
