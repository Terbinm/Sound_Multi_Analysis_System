"""
CycleGAN 域转换脚本

将 Domain A 的 LEAF 特征转换到 Domain B

使用方法：
    python scripts/convert.py --checkpoint checkpoints/best.ckpt --input data.json --output converted.json --direction AB
"""

import sys
import argparse
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import torch
import numpy as np

from models import CycleGANModule
from data import FileLEAFLoader
from utils import setup_logger


def main():
    parser = argparse.ArgumentParser(description="Convert LEAF features using trained CycleGAN")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to model checkpoint")
    parser.add_argument("--input", type=str, required=True, help="Input features file (JSON or NPY)")
    parser.add_argument("--output", type=str, required=True, help="Output file path")
    parser.add_argument("--direction", type=str, default="AB", choices=["AB", "BA"], help="Conversion direction")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="Device to use")
    args = parser.parse_args()

    # 设置日志
    logger = setup_logger()
    logger.info("=== CycleGAN Feature Conversion ===")

    # 检查设备
    if args.device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, using CPU")
        device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    # 加载模型
    logger.info(f"Loading model from {args.checkpoint}")
    model = CycleGANModule.load_from_checkpoint(args.checkpoint)
    model = model.to(device)
    model.eval()
    logger.info("Model loaded successfully")

    # 加載正規化參數
    checkpoint_path = Path(args.checkpoint)
    normalization_path = checkpoint_path.parent / 'normalization_params.json'

    normalization_params = None
    if normalization_path.exists():
        logger.info(f"Loading normalization parameters from {normalization_path}")
        with open(normalization_path, 'r', encoding='utf-8') as f:
            normalization_params = json.load(f)

        # 注意：使用統一歸一化時，mean_a = mean_b, std_a = std_b
        # 但為了向後兼容性，我們仍然根據方向選擇參數
        if args.direction == "AB":
            mean = np.array(normalization_params['mean_a'], dtype=np.float32)
            std = np.array(normalization_params['std_a'], dtype=np.float32)
            mean_target = np.array(normalization_params['mean_b'], dtype=np.float32)
            std_target = np.array(normalization_params['std_b'], dtype=np.float32)
            logger.info("Using Domain A normalization for input, Domain B for output")
        else:  # BA
            mean = np.array(normalization_params['mean_b'], dtype=np.float32)
            std = np.array(normalization_params['std_b'], dtype=np.float32)
            mean_target = np.array(normalization_params['mean_a'], dtype=np.float32)
            std_target = np.array(normalization_params['std_a'], dtype=np.float32)
            logger.info("Using Domain B normalization for input, Domain A for output")

        logger.info(f"  - Input: mean={mean[:3]}..., std={std[:3]}...")
        logger.info(f"  - Output: mean={mean_target[:3]}..., std={std_target[:3]}...")
    else:
        logger.warning(f"⚠ Normalization parameters not found at {normalization_path}")
        logger.warning("⚠ Converting without normalization (may produce poor results)")
        mean = None
        std = None
        mean_target = None
        std_target = None

    # 加载输入特征
    logger.info(f"Loading input features from {args.input}")
    if args.input.endswith('.json'):
        features_list = FileLEAFLoader.load_from_json(args.input)
    elif args.input.endswith('.npy'):
        features_list = FileLEAFLoader.load_from_npy(args.input)
    else:
        raise ValueError(f"Unsupported file format: {args.input}")

    logger.info(f"Loaded {len(features_list)} samples")

    # 转换特征
    logger.info(f"Converting features: {args.direction}")
    converted_features = []

    with torch.no_grad():
        for i, features in enumerate(features_list):
            # 正規化輸入特徵
            if mean is not None and std is not None:
                features_normalized = (features - mean) / std
            else:
                features_normalized = features

            # 转换为 Tensor
            feat_tensor = torch.FloatTensor(features_normalized).unsqueeze(0).to(device)

            # 执行转换
            if args.direction == "AB":
                converted = model.convert_A_to_B(feat_tensor)
            else:
                converted = model.convert_B_to_A(feat_tensor)

            # 转回 numpy
            converted_np = converted.squeeze(0).cpu().numpy()

            # 反正規化輸出特徵
            if mean_target is not None and std_target is not None:
                converted_np = converted_np * std_target + mean_target

            converted_features.append(converted_np)

            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(features_list)} samples")

    logger.info(f"Conversion completed: {len(converted_features)} samples")

    # 保存结果
    logger.info(f"Saving results to {args.output}")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.output.endswith('.json'):
        # 保存为 JSON
        output_data = [feat.tolist() for feat in converted_features]
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)
    elif args.output.endswith('.npy'):
        # 保存为 NPY
        FileLEAFLoader.save_to_npy(converted_features, args.output)
    else:
        raise ValueError(f"Unsupported output format: {args.output}")

    logger.info("=== Conversion Completed ===")


if __name__ == "__main__":
    main()
