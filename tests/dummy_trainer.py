import time
import sys

# A small script intended to be run as `python -m tests.dummy_trainer` during tests.
# It emits a few representative training progress lines to stdout and exits.

for i, pct in enumerate([5, 25, 50, 75, 100], start=1):
    print(f"Epoch: 1/1, Step: {i*10}/50 ({pct}%), loss: {0.5/(i)}, ETA: 00:0{5-i%5}")
    sys.stdout.flush()
    time.sleep(0.1)

print("Training finished for dummy_trainer")
