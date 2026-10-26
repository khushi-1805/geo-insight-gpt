from huggingface_hub import snapshot_download

model_path = snapshot_download(
    repo_id="ibm-nasa-geospatial/Prithvi-EO-1.0-100M-sen1floods11"
)

print("Model downloaded to:")
print(model_path)
