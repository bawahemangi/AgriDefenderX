from huggingface_hub import hf_hub_download

repo_id = "BiernyVR/crop-disease-classifier"

hf_hub_download(
    repo_id=repo_id,
    filename="efficientnet_v2_s_best.onnx",
    local_dir="disease_model"
)

hf_hub_download(
    repo_id=repo_id,
    filename="efficientnet_v2_s_best.onnx.data",
    local_dir="disease_model"
)

hf_hub_download(
    repo_id=repo_id,
    filename="classes.json",
    local_dir="disease_model"
)

print("Model downloaded successfully!")