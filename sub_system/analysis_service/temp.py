import torch, platform
print("torch:", torch.__version__)
print("CUDA built with:", torch.version.cuda)
print("is_built_with_cuda:", torch.backends.cuda.is_built())
print("cuda available:", torch.cuda.is_available())
print("device count:", torch.cuda.device_count())
print("python:", platform.python_version())

import torch
x = torch.randn(1024, 1024, device="cuda")
print(torch.cuda.get_device_name())
print(x @ x.T)  # 應該在 GPU 上跑
