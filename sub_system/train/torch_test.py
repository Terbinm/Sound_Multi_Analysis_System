import platform, json, sys
import torch

def header(t): print("\n" + "="*8 + f" {t} " + "="*8)

def ok(msg):  print(f"✅ {msg}")
def warn(msg):print(f"⚠️  {msg}")
def fail(msg):print(f"❌ {msg}")

def main():
    header("Environment / Versions")
    print("python:", platform.python_version())
    print("torch:", torch.__version__)
    print("CUDA built with:", torch.version.cuda)
    print("cuda available:", torch.cuda.is_available())
    print("cudnn available:", torch.backends.cudnn.is_available())
    try:
        print("cudnn version:", torch.backends.cudnn.version())
    except Exception:
        pass
    print("is_built_with_cuda:", torch.backends.cuda.is_built())
    print("device count:", torch.cuda.device_count())
    if torch.cuda.is_available() and torch.cuda.device_count() > 0:
        print("device name:", torch.cuda.get_device_name(0))
        props = torch.cuda.get_device_properties(0)
        print("total memory (GB):", round(props.total_memory / (1024**3), 2))

    # ---------- PyTorch CUDA sanity ----------
    header("PyTorch CUDA tensor test")
    try:
        x = torch.randn(1024, 1024, device="cuda")
        y = x @ x.T
        y.norm()  # touch result
        ok("PyTorch CUDA matmul OK")
    except Exception as e:
        fail(f"PyTorch CUDA test failed: {e}")

    # ---------- torchvision tests ----------
    header("torchvision tests")
    try:
        import torchvision, torchvision.ops, torchvision.models as models
        print("torchvision:", torchvision.__version__)
    except Exception as e:
        fail(f"import torchvision failed: {e}")
        torchvision = None

    if torchvision is not None and torch.cuda.is_available():
        # 1) model forward on GPU (no weights download)
        try:
            model = models.resnet18(weights=None).eval().to("cuda")
            dummy = torch.randn(1, 3, 224, 224, device="cuda")
            with torch.inference_mode():
                _ = model(dummy)
            ok("torchvision ResNet18 forward on CUDA OK")
        except Exception as e:
            fail(f"ResNet18 CUDA forward failed: {e}")

        # 2) CUDA kernel op: NMS
        try:
            from torchvision.ops import nms
            boxes = torch.rand(1000, 4, device="cuda")
            boxes[:, 2:] += boxes[:, :2]  # make x2>=x1, y2>=y1
            scores = torch.rand(1000, device="cuda")
            idx = nms(boxes, scores, iou_threshold=0.5)
            assert idx.is_cuda, "NMS output not on CUDA"
            ok("torchvision.ops.nms on CUDA OK")
        except Exception as e:
            warn(f"NMS CUDA test warning/failed (可能是 CPU fallback 或未編入 CUDA): {e}")

    header("Summary")
    print("完成。若上面各區塊皆為 ✅，代表 torch/vision 都能在 GPU 正常運作。")

if __name__ == "__main__":
    main()
