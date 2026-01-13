# processors/step2_leaf.py - LEAF 特徵提取器（使用 librosa MelSpectrogram）

import numpy as np
import librosa
from typing import List, Dict, Any, Optional, Tuple

from config import UPLOAD_FOLDER
from utils.logger import logger
import os


class LEAFFeatureExtractor:
    """LEAF 特徵提取器"""

    def __init__(self, leaf_config: Dict[str, Any], audio_config: Dict[str, Any]):
        """初始化 LEAF 提取器"""
        self.config = dict(leaf_config)
        self.audio_config = dict(audio_config)
        self._window_params = self._compute_window_params()

        logger.info("LEAF 提取器初始化成功 (使用 librosa MelSpectrogram)")
        win_length, hop_length, n_fft = self._window_params
        logger.debug(
            f"[Step 2] LEAF 特徵提取參數: "
            f"採樣率={self.config['sample_rate']}Hz, "
            f"視窗={self.config['window_len']}ms ({win_length}採樣點), "
            f"步進={self.config['window_stride']}ms ({hop_length}採樣點), "
            f"n_fft={n_fft}, "
            f"頻率範圍={self.config['init_min_freq']}-{self.config['init_max_freq']}Hz, "
            f"Mel濾波器={self.config['n_filters']}, "
            f"PCEN壓縮={self.config['pcen_compression']}"
        )

    def _compute_window_params(self) -> Tuple[int, int, int]:
        """計算 MelSpectrogram 需使用的視窗參數"""
        sample_rate = self.config['sample_rate']
        win_length = max(1, int(sample_rate * self.config['window_len'] / 1000))
        hop_length = max(1, int(sample_rate * self.config['window_stride'] / 1000))
        n_fft = 512
        logger.debug(
            f"[Step 2] LEAF 視窗參數計算: "
            f"win_length={win_length} (來自 {self.config['window_len']}ms @ {sample_rate}Hz), "
            f"hop_length={hop_length} (來自 {self.config['window_stride']}ms), "
            f"n_fft={n_fft}"
        )
        return win_length, hop_length, n_fft

    def apply_config(self, leaf_config: Dict[str, Any], audio_config: Dict[str, Any]):
        """更新參數"""
        if isinstance(leaf_config, dict):
            self.config.update(leaf_config)
        if isinstance(audio_config, dict):
            self.audio_config.update(audio_config)
        self._window_params = self._compute_window_params()
        logger.info(f"LEAF 配置已更新 (sample_rate={self.config['sample_rate']})")

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
            n_batches = (len(segments) + self.config['batch_size'] - 1) // self.config['batch_size']
            logger.debug(f"[Step 2] 特徵提取準備: 總切片={len(segments)}, 批次大小={self.config['batch_size']}, 批次數={n_batches}")

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

            return self._extract_with_librosa(audio_segment)

        except Exception as e:
            logger.error(f"Mel-Spectrogram 特徵提取失敗: {e}")
            return None

    def _extract_with_librosa(self, audio_segment: np.ndarray) -> Optional[np.ndarray]:
        """使用 librosa 生成 MelSpectrogram，無需 torchaudio"""
        try:
            win_length, hop_length, n_fft = self._window_params
            # logger.debug(
            #     f"[Step 2] Mel-Spectrogram 計算: "
            #     f"輸入長度={len(audio_segment)}採樣點, "
            #     f"n_fft={n_fft}, hop={hop_length}, win={win_length}, "
            #     f"n_mels={self.config['n_filters']}, "
            #     f"fmin={self.config['init_min_freq']}, fmax={self.config['init_max_freq']}"
            # )
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
            # logger.debug(f"[Step 2] Mel-Spectrogram 完成: shape={mel_spec.shape}, 特徵值範圍=[{features.min():.4f}, {features.max():.4f}]")
            return features.astype(np.float32)
        except Exception as exc:
            logger.error(f"librosa MelSpectrogram 計算失敗: {exc}")
            return None

    def get_feature_info(self) -> Dict[str, Any]:
        """獲取特徵提取器資訊"""
        return {
            'extractor_type': 'MelSpectrogram (librosa)',
            'feature_dtype': 'float32',
            'n_filters': self.config['n_filters'],
            'sample_rate': self.config['sample_rate'],
            'window_len': self.config['window_len'],
            'window_stride': self.config['window_stride'],
            'pcen_compression': self.config['pcen_compression'],
            'feature_dim': self.config['n_filters']
        }

    def cleanup(self):
        """清理資源"""
        logger.info("LEAF 提取器資源已清理")
