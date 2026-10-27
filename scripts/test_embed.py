import base64
import os

figs = [
    "docs/figures/figure_1_1.png",
    "docs/figures/figure_3_1.png",
    "docs/figures/figure_3_2.png",
    "docs/figures/figure_3_3.png",
    "docs/figures/figure_4_1.png",
    "docs/figures/figure_4_2.png",
]

for f in figs:
    sz = os.path.getsize(f)
    print(f"{f}: {sz} bytes")

print("All figure paths verified.")
