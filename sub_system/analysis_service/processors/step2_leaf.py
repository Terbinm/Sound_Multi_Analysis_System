# processors/step2_leaf.py - LEAF 特徵提取器（使用 torchaudio MelSpectrogram）

import torch
import torch.nn as nn
import numpy as np
import librosa
from typing import List, Dict, Any, Optional, Tuple

try:
    import torchaudio.transforms as T
    TORCHAUDIO_AVAILABLE = True
except ImportError:  # torchaudio 可能在部分 CUDA wheel 缺席
    T = None
    TORCHAUDIO_AVAILABLE = False

from config import UPLOAD_FOLDER
from utils.logger import logger
import os


class LEAFFeatureExtractor:
    """LEAF 特徵提取器"""

    def __init__(self, leaf_config: Dict[str, Any], audio_config: Dict[str, Any]):
        """初始化 LEAF 提取器"""
        self.config = dict(leaf_config)
        self.audio_config = dict(audio_config)
        self.device = self._resolve_device(self.config.get('device', 'cpu'))
        self._window_params = self._compute_window_params()
        self.use_torchaudio = TORCHAUDIO_AVAILABLE
        self.model = None

        if self.use_torchaudio:
            self.model = self._initialize_leaf_model()
        else:
            logger.warning(
                "torchaudio 未安裝或不支援當前 CUDA 版本，Step 2 將改用 librosa 特徵計算 (CPU)"
            )

        logger.info(f"LEAF 提取器初始化成功 (device={self.device})")

    def _resolve_device(self, device_name: str) -> torch.device:
        """確認裝置可用，若 CUDA 不可用則退回 CPU"""
        if str(device_name).startswith('cuda') and not torch.cuda.is_available():
            logger.warning("CUDA 裝置不可用，LEAF 提取器改用 CPU")
            return torch.device('cpu')
        return torch.device(device_name)

    def _compute_window_params(self) -> Tuple[int, int, int]:
        """計算 MelSpectrogram 需使用的視窗參數"""
        sample_rate = self.config['sample_rate']
        win_length = max(1, int(sample_rate * self.config['window_len'] / 1000))
        hop_length = max(1, int(sample_rate * self.config['window_stride'] / 1000))
        n_fft = 512
        return win_length, hop_length, n_fft

    def _initialize_leaf_model(self) -> nn.Module:
        """初始化 MelSpectrogram 模型（替代 LEAF）"""
        try:
            if not self.use_torchaudio or T is None:
                raise RuntimeError("torchaudio 不可用，無法初始化 GPU MelSpectrogram")

            win_length, hop_length, n_fft = self._window_params

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

    def apply_config(self, leaf_config: Dict[str, Any], audio_config: Dict[str, Any]):
        """更新參數並在需要時重建模型"""
        needs_reinit = False
        if isinstance(leaf_config, dict):
            if leaf_config.get('sample_rate') != self.config.get('sample_rate') or \
               leaf_config.get('n_filters') != self.config.get('n_filters') or \
               leaf_config.get('window_len') != self.config.get('window_len') or \
               leaf_config.get('window_stride') != self.config.get('window_stride'):
                needs_reinit = True
            self.config.update(leaf_config)
        if isinstance(audio_config, dict):
            self.audio_config.update(audio_config)
        if needs_reinit:
            self.device = self._resolve_device(self.config.get('device', 'cpu'))
            self._window_params = self._compute_window_params()
            if self.use_torchaudio:
                self.model = self._initialize_leaf_model()
            logger.info(f"LEAF 配置變更，已重建 MelSpectrogram (sample_rate={self.config['sample_rate']})")
        else:
            self._window_params = self._compute_window_params()

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

            logger.debug(f"開始提取 LEAF 特徵: {len(segments)} 個切片")

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
                sr=self.audio_config['sample_rate'],
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

            if self.use_torchaudio and self.model is not None:
                return self._extract_with_torchaudio(audio_tensor)

            return self._extract_with_librosa(audio_segment)

        except Exception as e:
            logger.error(f"Mel-Spectrogram 特徵提取失敗: {e}")
            return None

    def _extract_with_torchaudio(self, audio_tensor: torch.Tensor) -> Optional[np.ndarray]:
        """使用 torchaudio 取得 MelSpectrogram 特徵"""
        try:
            with torch.no_grad():
                mel_spec = self.model(audio_tensor)
                features = torch.mean(mel_spec, dim=-1)
                if self.config['pcen_compression']:
                    features = torch.log(features + 1e-6)
                return features.cpu().numpy()
        except Exception as exc:
            logger.error(f"torchaudio MelSpectrogram 計算失敗，將回退 librosa: {exc}")
            return self._extract_with_librosa(audio_tensor.cpu().numpy())

    def _extract_with_librosa(self, audio_segment: np.ndarray) -> Optional[np.ndarray]:
        """使用 librosa 生成 MelSpectrogram，無需 torchaudio"""
        try:
            win_length, hop_length, n_fft = self._window_params
            mel_spec = librosa.feature.melspectrogram(
                y=audio_segment,
                sr=self.config['sample_rate'],
                n_fft=n_fft,
                hop_length=hop_length,
                win_length=win_length,
                fmin=self.config['init_min_freq'],
                fmax=self.config['init_max_freq'],
                n_mels=self.config['n_filters'],
                power=2.0
            )

            features = np.mean(mel_spec, axis=-1)
            if self.config['pcen_compression']:
                features = np.log(features + 1e-6)
            return features.astype(np.float32)
        except Exception as exc:
            logger.error(f"librosa MelSpectrogram 計算失敗: {exc}")
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
