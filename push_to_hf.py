#!/usr/bin/env python3
"""Upload the dataset card and every release's runs.jsonl to Hugging Face.

Requires HF_TOKEN (or `hf auth login`) and HF_DATASET_REPO, e.g. "user/frogs".
Idempotent: create_repo(exist_ok=True) and content-addressed uploads.
"""

import os

from huggingface_hub import HfApi

REPO = os.environ["HF_DATASET_REPO"]
api = HfApi()

api.create_repo(REPO, repo_type="dataset", exist_ok=True)

api.upload_file(
    path_or_fileobj="hf/README.md",
    path_in_repo="README.md",
    repo_id=REPO,
    repo_type="dataset",
)

api.upload_folder(
    folder_path="results",
    path_in_repo="data",
    repo_id=REPO,
    repo_type="dataset",
    commit_message="Add run data",
    ignore_patterns=["*/raw/*"],   # raw responses stay in the git repo only
)

print(f"pushed to https://huggingface.co/datasets/{REPO}")
