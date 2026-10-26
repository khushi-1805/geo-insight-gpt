from terratorch.registry import BACKBONE_REGISTRY


print("Loading Prithvi flood model...")

model = BACKBONE_REGISTRY.build(
    "hf-hub:ibm-nasa-geospatial/Prithvi-EO-1.0-100M-sen1floods11"
)

print("Model loaded successfully!")
print(model)