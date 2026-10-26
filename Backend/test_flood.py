import numpy as np
import torch

from flood.preprocessing import load_flood_bands
from flood.prithvi_model import load_flood_model


IMAGE_DIR = "flood_data"


print("Loading Sentinel-2 data...")

image = load_flood_bands(IMAGE_DIR)

print("Image shape:", image.shape)


# -----------------------------------------
# Create 224 x 224 patch
# -----------------------------------------

_, height, width = image.shape

y = max((height - 224) // 2, 0)
x = max((width - 224) // 2, 0)

patch = image[:, y:y + 224, x:x + 224]

print("Patch shape:", patch.shape)


# -----------------------------------------
# Torch tensor
# -----------------------------------------

tensor = torch.from_numpy(
    patch.astype(np.float32)
).unsqueeze(0)

print("Tensor shape:", tensor.shape)


# -----------------------------------------
# Load model
# -----------------------------------------

model = load_flood_model()


# -----------------------------------------
# Inference
# -----------------------------------------

print("Running flood inference...")

with torch.no_grad():
    output = model(tensor)

print("Raw output type:", type(output))

if isinstance(output, dict):
    output = output["out"]

if isinstance(output, (list, tuple)):
    output = output[0]

print("Output shape:", output.shape)


# -----------------------------------------
# Flood mask
# -----------------------------------------

mask = torch.argmax(output, dim=1)

mask = mask.squeeze(0).cpu().numpy()

print("Flood mask shape:", mask.shape)

print("Classes detected:", np.unique(mask))


# -----------------------------------------
# Flood percentage
# -----------------------------------------

flood_pixels = np.sum(mask == 1)
total_pixels = mask.size

flood_percentage = (
    flood_pixels / total_pixels
) * 100

print(
    f"Flooded area: {flood_percentage:.2f}%"
)