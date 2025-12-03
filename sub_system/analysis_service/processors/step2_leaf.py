# processors/step2_leaf.py - LEAF 特徵提取器（使用 torchaudio MelSpectrogram）

import torch
import torch.nn as nn
import numpy as np
import librosa
from typing import List, Dict, Any, Optional
import torchaudio.transforms as T
from config import LEAF_CONFIG, AUDIO_CONFIG, UPLOAD_FOLDER
from utils.logger import logger
import os


class LEAFFeatureExtractor:
    """LEAF 特徵提取器"""

    def __init__(self):
        """初始化 LEAF 提取器"""
        self.config = LEAF_CONFIG
        self.device = torch.device(self.config['device'])
        self.model = self._initialize_leaf_model()

        logger.info(f"LEAF 提取器初始化成功 (device={self.device})")

    def _initialize_leaf_model(self) -> nn.Module:
        """初始化 MelSpectrogram 模型（替代 LEAF）"""
        try:
            # 计算窗口参数（毫秒转换为样本数）
            win_length = int(self.config['sample_rate'] * self.config['window_len'] / 1000)
            hop_length = int(self.config['sample_rate'] * self.config['window_stride'] / 1000)
            n_fft = 512  # 使用 512 点 FFT

            # 创建 MelSpectrogram 转换
            mel_spectrogram = T.MelSpectrogram(
                sample_rate=self.config['sample_rate'],
                n_fft=n_fft,
                win_length=win_length,
                hop_length=hop_length,
                f_min=self.config['init_min_freq'],
                f_max=self.config['init_max_freq'],
                n_mels=self.config['n_filters'],
                power=2.0  # 能量谱
            ).to(self.device)

            logger.info(f"MelSpectrogram 初始化成功 (n_mels={self.config['n_filters']}, device={self.device})")
            logger.debug(f"參數: win_length={win_length}, hop_length={hop_length}, n_fft={n_fft}")
            return mel_spectrogram

        except Exception as e:
            logger.error(f"MelSpectrogram 初始化失敗: {e}")
            raise

    def _count_parameters(self, model: nn.Module) -> int:
        """計算模型參數數量"""
        return sum(p.numel() for p in model.parameters() if p.requires_grad)

    def extract_features(self, filepath: str, segments: List[Dict]) -> List[List[float]]:
        """
        提取所有切片的 LEAF 特徵

        Args:
            filepath: 音訊檔案路徑
            segments: 切片資訊列表

        Returns:
            純特徵向量列表 [[feat1], [feat2], ...]
        """
        try:
            if not segments:
                logger.warning(f"沒有切片資料: {filepath}")
                return []

            logger.info(f"開始提取 LEAF 特徵: {len(segments)} 個切片")

            features_data = []

            # 批次處理切片
            for i in range(0, len(segments), self.config['batch_size']):
                batch_segments = segments[i:i + self.config['batch_size']]
                batch_features = self._extract_batch(filepath, batch_segments)
                features_data.extend(batch_features)

            logger.info(
                f"LEAF 特徵提取完成: {len(features_data)} 個切片，特徵維度={self.config['n_filters']}"
            )
            return features_data

        except Exception as e:
            logger.error(f"LEAF 特徵提取失敗 {filepath}: {e}")
            return []

    def _extract_batch(self, filepath: str, segments: List[Dict]) -> List[List[float]]:
        """
        批次提取特徵

        Args:
            filepath: 音訊檔案路徑
            segments: 切片資訊列表

        Returns:
            特徵向量列表
        """
        batch_features = []

        for segment_info in segments:
            try:
                # 載入音訊切片
                audio_segment = self._load_audio_segment(
                    filepath,
                    segment_info['start'],
                    segment_info['end'],
                    segment_info['channel']
                )

                if audio_segment is None:
                    logger.warning(f"無法載入切片: selec={segment_info['selec']}, 使用空特徵")
                    # 使用零向量代替
                    feature_vector = [0.0] * self.config['n_filters']
                else:
                    # 提取特徵
                    features = self._extract_single_segment(audio_segment)

                    if features is not None:
                        feature_vector = features.tolist()
                    else:
                        logger.warning(f"特徵提取失敗: selec={segment_info['selec']}, 使用空特徵")
                        feature_vector = [0.0] * self.config['n_filters']

                batch_features.append(feature_vector)

            except Exception as e:
                logger.error(f"提取特徵失敗 (selec={segment_info['selec']}): {e}")
                # 異常時使用零向量
                batch_features.append([0.0] * self.config['n_filters'])

        return batch_features

    def _load_audio_segment(self, filepath: str, start_time: float,
                            end_time: float, channel: int) -> Optional[np.ndarray]:
        """
        載入音訊切片

        Args:
            filepath: 音訊檔案路徑
            start_time: 開始時間（秒）
            end_time: 結束時間（秒）
            channel: 通道編號

        Returns:
            音訊切片或 None
        """
        try:
            # 載入音訊檔案
            audio, sr = librosa.load(
                filepath,
                sr=AUDIO_CONFIG['sample_rate'],
                mono=False,
                offset=start_time,
                duration=end_time - start_time
            )

            # 處理多通道
            if audio.ndim == 1:
                if channel != 0:
                    logger.warning(f"請求通道 {channel} 但音訊是單聲道")
                    return None
                return audio
            else:
                if channel >= audio.shape[0]:
                    logger.warning(f"請求通道 {channel} 超出範圍 {audio.shape[0]}")
                    return None
                return audio[channel]

        except Exception as e:
            logger.error(f"音訊載入失敗 {filepath}: {e}")
            return None

    def _extract_single_segment(self, audio_segment: np.ndarray) -> Optional[np.ndarray]:
        """
        提取單個音訊切片的 Mel-Spectrogram 特徵

        Args:
            audio_segment: 音訊切片 (1D numpy array)

        Returns:
            Mel-Spectrogram 特徵向量或 None
        """
        try:
            # 檢查音訊長度
            min_samples = int(self.config['sample_rate'] * 0.025)
            if len(audio_segment) < min_samples:
                logger.warning(f"音訊切片太短: {len(audio_segment)} < {min_samples}")
                return None

            # 轉換為 PyTorch 張量 [samples]
            audio_tensor = torch.FloatTensor(audio_segment).to(self.device)

            # 提取 MelSpectrogram 特徵
            with torch.no_grad():
                # MelSpectrogram 輸出: (n_mels, time)
                mel_spec = self.model(audio_tensor)

                # 對時間維度取平均，得到 (n_mels,) 的特徵向量
                features = torch.mean(mel_spec, dim=-1)

                # 應用 log 壓縮（類似 PCEN）
                if self.config['pcen_compression']:
                    features = torch.log(features + 1e-6)

                features_np = features.cpu().numpy()

                return features_np

        except Exception as e:
            logger.error(f"Mel-Spectrogram 特徵提取失敗: {e}")
            return None

    def get_feature_info(self) -> Dict[str, Any]:
        """獲取特徵提取器資訊"""
        return {
            'extractor_type': 'MelSpectrogram',
            'feature_dtype': 'float32',
            'n_filters': self.config['n_filters'],
            'sample_rate': self.config['sample_rate'],
            'window_len': self.config['window_len'],
            'window_stride': self.config['window_stride'],
            'pcen_compression': self.config['pcen_compression'],
            'device': str(self.device),
            'feature_dim': self.config['n_filters']
        }

    def cleanup(self):
        """清理資源"""
        if hasattr(self, 'model'):
            del self.model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("LEAF 提取器資源已清理")
