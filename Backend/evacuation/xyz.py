
import torch
from pathlib import Path
from collections import Counter

checkpoint_path = Path(
    r"C:\Users\Khushi Kalinge\.cache\huggingface\hub\models--ibm-nasa-geospatial--Prithvi-EO-1.0-100M-sen1floods11\snapshots\86668a4feac50e0b6ce5f373c06297187fe20e33\sen1floods11_Prithvi_100M.pth"
)

checkpoint = torch.load(
    checkpoint_path,
    map_location="cpu",
    weights_only=False
)

state_dict = checkpoint["state_dict"]

print("\n========== CHECKPOINT METADATA ==========")
print(checkpoint["meta"])

print("\n========== PARAMETER GROUPS ==========")

groups = Counter()

for key in state_dict:
    prefix = key.split(".")[0]
    groups[prefix] += 1

for name, count in groups.items():
    print(f"{name}: {count} parameters")

print("\n========== NON-BACKBONE PARAMETERS ==========")

for key, value in state_dict.items():
    if not key.startswith("backbone."):
        shape = tuple(value.shape) if hasattr(value, "shape") else type(value)
        print(key, shape)

print("\n========== TOTAL PARAMETERS ==========")
print("Total tensors:", len(state_dict))
