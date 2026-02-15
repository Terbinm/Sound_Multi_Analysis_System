# processors/step2_statistical_features.py - 統計特徵提取器（12 維）
#
# 參考 Models_training/data_preprocessing/tdms_preprocessing/feature_extractor.py
# 用於 TDMS 訊號的統計特徵提取，與 Models_training 訓練邏輯完全一致

import numpy as np
from scipy import stats
from scipy.signal import hilbert
from typing import List, Dict, Any, Optional, Union
from utils.logger import logger


class StatisticalFeatureExtractor:
    """
    12 維統計特徵提取器

    特徵列表:
    - 時域特徵 (5):
        1. rms - 均方根
        2. peak_to_peak - 峰峰值
        3. kurtosis - 峰度
        4. skewness - 偏度
        5. crest_factor - 波峰因子

    - 頻域特徵 (4):
        6. spectral_centroid - 頻譜質心
        7. spectral_bandwidth - 頻譜帶寬
        8. dominant_frequency - 主頻
        9. spectral_rolloff - 頻譜滾降點 (85%)

    - 包絡特徵 (3):
        10. envelope_mean - 包絡均值
        11. envelope_std - 包絡標準差
        12. zero_crossing_rate - 過零率
    """

    FEATURE_DIM = 12
    FEATURE_NAMES = [
        'rms', 'peak_to_peak', 'kurtosis', 'skewness', 'crest_factor',
        'spectral_centroid', 'spectral_bandwidth', 'dominant_frequency', 'spectral_rolloff',
        'envelope_mean', 'envelope_std', 'zero_crossing_rate'
    ]

    def __init__(self, sample_rate: int = 10000):
        """
        初始化統計特徵提取器

        Args:
            sample_rate: 取樣率 (Hz)，預設 10000
        """
        self.sample_rate = sample_rate
        logger.info(f"StatisticalFeatureExtractor 初始化: sample_rate={sample_rate}Hz, feature_dim={self.FEATURE_DIM}")

    def apply_config(self, config: Dict[str, Any]):
        """
        更新配置

        Args:
            config: 配置字典，可包含 sample_rate
        """
        if isinstance(config, dict):
            if 'sample_rate' in config:
                self.sample_rate = int(config['sample_rate'])
                logger.info(f"StatisticalFeatureExtractor 配置更新: sample_rate={self.sample_rate}Hz")

    def extract_features(
        self,
        slices: List[Union[np.ndarray, Dict[str, Any]]]
    ) -> List[List[float]]:
        """
        對每個切片提取 12 維統計特徵

        Args:
            slices: 切片列表，可以是:
                - List[np.ndarray]: 純 numpy array 列表
                - List[Dict]: 包含 'data' 鍵的字典列表（來自 slice_signal()）

        Returns:
            特徵列表 [[12維特徵], [12維特徵], ...]
        """
        try:
            if not slices:
                logger.warning("沒有切片資料")
                return []

            features = []
            for i, slice_item in enumerate(slices):
                # 支援兩種輸入格式
                if isinstance(slice_item, dict):
                    signal = slice_item.get('data')
                else:
                    signal = slice_item

                if signal is None or len(signal) == 0:
                    logger.warning(f"切片 {i+1} 資料為空，使用零向量")
                    features.append([0.0] * self.FEATURE_DIM)
                    continue

                feat = self._extract_single(signal)
                features.append(feat)

            logger.info(f"統計特徵提取完成: {len(features)} 個切片，特徵維度={self.FEATURE_DIM}")
            return features

        except Exception as e:
            logger.error(f"統計特徵提取失敗: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_single(self, signal: np.ndarray) -> List[float]:
        """
        提取單個切片的 12 維統計特徵

        與 Models_training/data_preprocessing/tdms_preprocessing/feature_extractor.py 完全一致

        Args:
            signal: 訊號數據 (1D numpy array)

        Returns:
            12 維特徵列表
        """
        features = []

        try:
            signal = np.asarray(signal, dtype=np.float32)

            # ===== 時域特徵 (5) =====

            # 1. RMS (均方根)
            rms = np.sqrt(np.mean(signal ** 2))
            features.append(float(rms))

            # 2. Peak-to-Peak (峰峰值)
            peak_to_peak = float(np.max(signal) - np.min(signal))
            features.append(peak_to_peak)

            # 3. Kurtosis (峰度)
            kurtosis = float(stats.kurtosis(signal))
            features.append(kurtosis)

            # 4. Skewness (偏度)
            skewness = float(stats.skew(signal))
            features.append(skewness)

            # 5. Crest Factor (波峰因子)
            crest_factor = float(np.max(np.abs(signal)) / rms) if rms > 0 else 0.0
            features.append(crest_factor)

            # ===== 頻域特徵 (4) =====

            # FFT 計算
            fft = np.fft.rfft(signal)
            freqs = np.fft.rfftfreq(len(signal), 1 / self.sample_rate)
            magnitude = np.abs(fft)

            magnitude_sum = np.sum(magnitude)

            # 6. Spectral Centroid (頻譜質心)
            if magnitude_sum > 0:
                spectral_centroid = float(np.sum(freqs * magnitude) / magnitude_sum)
            else:
                spectral_centroid = 0.0
            features.append(spectral_centroid)

            # 7. Spectral Bandwidth (頻譜帶寬)
            if magnitude_sum > 0:
                spectral_bandwidth = float(np.sqrt(
                    np.sum(((freqs - spectral_centroid) ** 2) * magnitude) / magnitude_sum
                ))
            else:
                spectral_bandwidth = 0.0
            features.append(spectral_bandwidth)

            # 8. Dominant Frequency (主頻)
            dominant_frequency = float(freqs[np.argmax(magnitude)])
            features.append(dominant_frequency)

            # 9. Spectral Rolloff (頻譜滾降點 85%)
            cumsum = np.cumsum(magnitude)
            if cumsum[-1] > 0:
                rolloff_idx = np.searchsorted(cumsum, 0.85 * cumsum[-1])
                spectral_rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])
            else:
                spectral_rolloff = 0.0
            features.append(spectral_rolloff)

            # ===== 包絡特徵 (3) =====

            # Hilbert 變換取包絡
            analytic_signal = hilbert(signal)
            envelope = np.abs(analytic_signal)

            # 10. Envelope Mean (包絡均值)
            envelope_mean = float(np.mean(envelope))
            features.append(envelope_mean)

            # 11. Envelope Std (包絡標準差)
            envelope_std = float(np.std(envelope))
            features.append(envelope_std)

            # 12. Zero Crossing Rate (過零率)
            zero_crossings = np.sum(np.abs(np.diff(np.sign(signal))) > 0)
            zero_crossing_rate = float(zero_crossings / len(signal))
            features.append(zero_crossing_rate)

            return features

        except Exception as e:
            logger.error(f"單一切片特徵提取失敗: {e}")
            return [0.0] * self.FEATURE_DIM

    def get_feature_info(self) -> Dict[str, Any]:
        """
        獲取特徵提取器資訊

        Returns:
            特徵提取器資訊字典
        """
        return {
            'extractor_type': 'StatisticalFeatures',
            'feature_dtype': 'float32',
            'feature_dim': self.FEATURE_DIM,
            'feature_names': self.FEATURE_NAMES,
            'sample_rate': self.sample_rate,
            'description': '12-dimensional statistical features for vibration signal analysis'
        }

    def cleanup(self):
        """清理資源（此提取器無需特別清理）"""
        logger.info("StatisticalFeatureExtractor 資源已清理")
