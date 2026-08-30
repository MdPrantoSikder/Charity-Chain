"""
consensus.py — the consensus SWITCH.

Every part of the application imports its consensus from here. Which protocol
actually loads is decided by one environment variable:

    CONSENSUS=cbbft     (default -- the proposed mechanism)
    CONSENSUS=raft
    CONSENSUS=pbft

Nothing else in the system changes: same database, same donations, same nodes,
same escrow rules, same API. Only the consensus module is different, which is
exactly what makes the comparison fair -- any difference in the recorded
numbers is caused by the algorithm and nothing else.
"""

import os

PROTOCOL = os.getenv("CONSENSUS", "cbbft").lower()

if PROTOCOL == "raft":
    from raft_engine import (NodeAttributes, run_l1_to_l5, run_l6_to_l8,
                             run_l9, elect_leader, LAST_ROUND)
elif PROTOCOL == "pbft":
    from pbft_engine import (NodeAttributes, run_l1_to_l5, run_l6_to_l8,
                             run_l9, elect_leader, LAST_ROUND)
else:
    PROTOCOL = "cbbft"
    from cbbft_engine import (NodeAttributes, run_l1_to_l5, run_l6_to_l8,
                              run_l9, elect_leader, LAST_ROUND)

ACTIVE = {"cbbft": "CB-BFT", "raft": "Raft", "pbft": "PBFT"}[PROTOCOL]

__all__ = ["NodeAttributes", "run_l1_to_l5", "run_l6_to_l8", "run_l9",
           "elect_leader", "PROTOCOL", "ACTIVE", "LAST_ROUND"]