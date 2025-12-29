"""
CycleGAN 訓練腳本

使用方法：
    python scripts/train.py [--resume CHECKPOINT_PATH]

環境變量配置示例：
    export DOMAIN_A_DEVICE_ID=device_001
    export DOMAIN_B_DEVICE_ID=device_002
    export MAX_EPOCHS=200
    export BATCH_SIZE=32
"""

import sys
import argparse
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytorch_lightning as pl
from pytorch_lightning.loggers import TensorBoardLogger
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping
from torch.utils.data import DataLoader, random_split

from models import CycleGANModule
from data import LEAFDomainDataset, MongoDBLEAFLoader, FileLEAFLoader
from utils import setup_logger, get_config, validate_config


def main():
    parser = argparse.ArgumentParser(description="Train CycleGAN for LEAF feature domain adaptation")
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint")
    parser.add_argument("--print-config", action="store_true", help="Print configuration and exit")
    args = parser.parse_args()

    # 獲取配置
    config = get_config()

    # 打印配置並退出
    if args.print_config:
        from config import print_config
        print_config()
        return

    # 驗證配置
    try:
        validate_config()
    except ValueError as e:
        print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)

    # 設置日誌
    log_config = config['logging']
    logger = setup_logger(
        name="cyclegan",
        log_file=log_config['log_file'],
        level=getattr(__import__('logging'), log_config['level'])
    )
    logger.info("=== Starting CycleGAN Training ===")

    # 加載數據
    logger.info("Loading data...")
    data_config = config['data']
    mongodb_config = config['mongodb']

    loader = None
    try:
        if data_config['source'] == 'mongodb':
            loader = MongoDBLEAFLoader(mongodb_config)
            data = loader.load_dual_domain(
                domain_a_query=data_config['domain_a']['mongo_query'],
                domain_b_query=data_config['domain_b']['mongo_query'],
                max_samples_a=data_config['domain_a'].get('max_samples'),
                max_samples_b=data_config['domain_b'].get('max_samples')
            )

            domain_a_features = data['domain_a']
            domain_b_features = data['domain_b']
        else:
            # 從檔案載入
            domain_a_features = FileLEAFLoader.load_from_json(
                data_config['domain_a']['file_path']
            )
            domain_b_features = FileLEAFLoader.load_from_json(
                data_config['domain_b']['file_path']
            )
    finally:
        if loader is not None:
            loader.close()

    logger.info(f"Loaded {len(domain_a_features)} samples from Domain A")
    logger.info(f"Loaded {len(domain_b_features)} samples from Domain B")

    # 創建數據集
    preprocessing = data_config['preprocessing']
    full_dataset = LEAFDomainDataset(
        domain_a_features=domain_a_features,
        domain_b_features=domain_b_features,
        normalize=preprocessing['normalize'],
        augment=preprocessing['augment'],
        max_sequence_length=preprocessing.get('max_sequence_length')
    )

    # 劃分訓練/驗證集
    val_config = config['validation']
    val_split = val_config['val_split']
    val_size = int(len(full_dataset) * val_split)
    train_size = len(full_dataset) - val_size

    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])

    logger.info(f"Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}")

    # 創建 DataLoader
    train_config = config['training']
    train_loader = DataLoader(
        train_dataset,
        batch_size=train_config['batch_size'],
        shuffle=True,
        num_workers=train_config['num_workers'],
        pin_memory=True
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=train_config['batch_size'],
        shuffle=False,
        num_workers=train_config['num_workers'],
        pin_memory=True
    )

    # 創建模型
    logger.info("Creating model...")
    model_config = config['model']
    model = CycleGANModule(
        input_dim=model_config['input_dim'],
        generator_config=model_config['generator'],
        discriminator_config=model_config['discriminator'],
        lr_g=train_config['lr_g'],
        lr_d=train_config['lr_d'],
        beta1=train_config['beta1'],
        beta2=train_config['beta2'],
        lambda_cycle=train_config['lambda_cycle'],
        lambda_cycle_a=train_config.get('lambda_cycle_a'),
        lambda_cycle_b=train_config.get('lambda_cycle_b'),
        lambda_identity=train_config['lambda_identity'],
        lambda_fm=train_config['lambda_fm'],
        use_identity_loss=train_config['use_identity_loss']
    )

    # 設置 Callbacks
    callbacks = []

    # ModelCheckpoint
    checkpoint_config = train_config['checkpoint']
    checkpoint_callback = ModelCheckpoint(
        dirpath=checkpoint_config['save_dir'],
        filename='cyclegan-{epoch:02d}-{val/cycle_A:.4f}',
        monitor=checkpoint_config['monitor'],
        mode=checkpoint_config['mode'],
        save_top_k=checkpoint_config['save_top_k'],
        save_last=True
    )
    callbacks.append(checkpoint_callback)

    # EarlyStopping
    es_config = train_config['early_stopping']
    if es_config['enabled']:
        early_stop_callback = EarlyStopping(
            monitor=es_config['monitor'],
            patience=es_config['patience'],
            mode=es_config['mode']
        )
        callbacks.append(early_stop_callback)

    # 設置 Logger
    tb_logger = TensorBoardLogger(
        save_dir=log_config['log_dir'],
        name="cyclegan"
    )

    # 創建 Trainer
    logger.info("Creating trainer...")
    hardware_config = config['hardware']
    trainer = pl.Trainer(
        max_epochs=train_config['max_epochs'],
        accelerator=hardware_config['accelerator'],
        devices=hardware_config['devices'],
        precision=hardware_config['precision'],
        logger=tb_logger,
        callbacks=callbacks,
        log_every_n_steps=log_config['log_every_n_steps'],
        check_val_every_n_epoch=val_config['check_val_every_n_epoch']
    )

    # 開始訓練
    logger.info("=== Starting Training ===")
    logger.info(f"Configuration:")
    logger.info(f"  - Epochs: {train_config['max_epochs']}")
    logger.info(f"  - Batch size: {train_config['batch_size']}")
    logger.info(f"  - Learning rate G (lr_g): {train_config['lr_g']}")
    logger.info(f"  - Learning rate D (lr_d): {train_config['lr_d']}")
    lambda_cycle_a = train_config.get('lambda_cycle_a', train_config['lambda_cycle'])
    lambda_cycle_b = train_config.get('lambda_cycle_b', train_config['lambda_cycle'])
    logger.info(
        "  - Lambda cycle (base/A/B): "
        f"{train_config['lambda_cycle']} / {lambda_cycle_a} / {lambda_cycle_b}"
    )
    logger.info(f"  - Lambda identity: {train_config['lambda_identity']}")
    logger.info(f"  - Device: {hardware_config['accelerator']}")

    trainer.fit(model, train_loader, val_loader, ckpt_path=args.resume)

    logger.info("=== Training Completed ===")
    logger.info(f"Best model saved at: {checkpoint_callback.best_model_path}")

    # 儲存正規化參數
    logger.info("Saving normalization parameters...")
    normalization_params = full_dataset.get_normalization_params()

    if normalization_params:
        import json
        from pathlib import Path

        # 將 numpy array 轉換為 list 以便 JSON 序列化
        params_to_save = {}
        for key, value in normalization_params.items():
            if hasattr(value, 'tolist'):
                params_to_save[key] = value.tolist()
            else:
                params_to_save[key] = value

        # 儲存到 checkpoint 目錄
        checkpoint_dir = Path(checkpoint_config['save_dir'])
        normalization_path = checkpoint_dir / 'normalization_params.json'

        with open(normalization_path, 'w', encoding='utf-8') as f:
            json.dump(params_to_save, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Normalization parameters saved to: {normalization_path}")
        logger.info(f"  - Domain A: mean={params_to_save['mean_a'][:3]}..., std={params_to_save['std_a'][:3]}...")
        logger.info(f"  - Domain B: mean={params_to_save['mean_b'][:3]}..., std={params_to_save['std_b'][:3]}...")
    else:
        logger.warning("⚠ Normalization was disabled during training, no parameters to save")


if __name__ == "__main__":
    main()
