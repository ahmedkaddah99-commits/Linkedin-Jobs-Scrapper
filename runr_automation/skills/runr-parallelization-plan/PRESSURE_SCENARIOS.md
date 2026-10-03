# Pressure scenarios

Baseline risks: assigning both tickets to Wave 01 because no explicit edge exists, deleting a user relation that conflicts with inference, and keeping wave labels after inputs changed.

1. No edge, same migration file. Expected: separate waves.
2. Inferred graph omits a user edge. Expected: preserve user edge and report disagreement.
3. A dependency cycle exists. Expected: no wave; review required with cycle evidence.
