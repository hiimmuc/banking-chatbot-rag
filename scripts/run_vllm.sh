#!/usr/bin/env bash
# Local Qwen3.5-2B on an 8 GB GPU, driver 570 (CUDA 12.8). Needs the cu129 image: the default image is CUDA 13 and fails with error 804.
# - removes the image's CUDA forward-compat libs (they break on GeForce GPUs)
# - removes torchcodec (built for CUDA 13, breaks the Qwen3.5 processor import)
# - disables image/video inputs: skips ~2 GB of multimodal profiling so the KV cache fits
HF="${HF_HOME:-$HOME/huggingface}"; HF="${HF/#\~/$HOME}"  # docker rejects a literal ~
docker rm -f vllm-qwen >/dev/null 2>&1
docker run -d --restart unless-stopped --name vllm-qwen --gpus all -p 127.0.0.1:8000:8000 \
  -v "$HF":/root/.cache/huggingface -e HF_HUB_OFFLINE=1 \
  --entrypoint bash vllm/vllm-openai:v0.32.0-cu129 -c "rm -rf /usr/local/cuda/compat /usr/local/cuda-*/compat; ldconfig; pip uninstall -y torchcodec >/dev/null 2>&1; \
  exec vllm serve Qwen/Qwen3.5-2B --served-model-name Qwen/Qwen3.5-2B --max-model-len 6144 --gpu-memory-utilization 0.40 \
  --quantization fp8_per_tensor --enforce-eager --max-num-seqs 4 --max-num-batched-tokens 2048 \
  --limit-mm-per-prompt '{\"image\":0,\"video\":0}' --reasoning-parser qwen3 --host 0.0.0.0"
