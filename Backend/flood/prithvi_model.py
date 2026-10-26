import torch
from pathlib import Path
from terratorch.registry import BACKBONE_REGISTRY


MODEL_DIR = Path(
    r"C:\Users\Khushi Kalinge\.cache\huggingface\hub\models--ibm-nasa-geospatial--Prithvi-EO-1.0-100M-sen1floods11\snapshots\86668a4feac50e0b6ce5f373c06297187fe20e33"
)

CHECKPOINT = MODEL_DIR / "sen1floods11_Prithvi_100M.pth"


def load_flood_model():

    print("Building Prithvi backbone...")

    model = BACKBONE_REGISTRY.build(
        "terratorch_prithvi_eo_v1_100",
        pretrained=False,
        in_chans=6,
        img_size=224,
    )

    print("Loading flood checkpoint...")

    checkpoint = torch.load(
        CHECKPOINT,
        map_location="cpu",
        weights_only=False,
    )

    # Inspect checkpoint structure
    if isinstance(checkpoint, dict):
        print("Checkpoint keys:", checkpoint.keys())

    if "state_dict" in checkpoint:
        state_dict = checkpoint["state_dict"]
    else:
        state_dict = checkpoint

    # Remove prefixes if present
    cleaned_state_dict = {}

    for key, value in state_dict.items():
        key = key.replace("module.", "")
        key = key.replace("backbone.", "")
        cleaned_state_dict[key] = value

    result = model.load_state_dict(
        cleaned_state_dict,
        strict=False,
    )

    print("Missing keys:", len(result.missing_keys))
    print("Unexpected keys:", len(result.unexpected_keys))

    model.eval()

    print("PRITHVI FLOOD MODEL LOADED")

    return model

def predict_flood(image):
    """
    image: numpy array with shape (6, H, W)
    """

    import numpy as np

    model = load_flood_model()

    # Convert numpy -> torch
    tensor = torch.from_numpy(
        np.asarray(image, dtype=np.float32)
    )

    # Center crop to Prithvi's required 224x224 input
    _, h, w = tensor.shape

    y = max((h - 224) // 2, 0)
    x = max((w - 224) // 2, 0)

    tensor = tensor[:, y:y + 224, x:x + 224]

    # Add batch dimension
    tensor = tensor.unsqueeze(0)

    with torch.no_grad():
        features = model(tensor)

    return features