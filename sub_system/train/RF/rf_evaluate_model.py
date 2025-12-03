# regrassion_evaluate_model.py - 模型評估工具

import os
import sys
import numpy as np
import pickle
import json
from pathlib import Path
from typing import Dict, Tuple
import logging

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_recall_fscore_support,
    roc_auc_score
)
import matplotlib.pyplot as plt
import seaborn as sns

# 重用訓練腳本的部分功能
from train_rf_model import DataLoader, ModelConfig, ResultVisualizer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelEvaluator:
    """模型評估器"""
    
    def __init__(self, model_dir: str):
        """
        初始化評估器
        
        Args:
            model_dir: 模型目錄
        """
        self.model_dir = Path(model_dir)
        self.model = None
        self.scaler = None
        self.metadata = None
        
        self._load_model()
    
    def _load_model(self):
        """載入模型"""
        try:
            # 載入模型
            model_path = self.model_dir / 'rf_classifier.pkl'
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            logger.info(f"✓ 模型載入成功: {model_path}")
            
            # 載入 Scaler
            scaler_path = self.model_dir / 'feature_scaler.pkl'
            if scaler_path.exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info(f"✓ Scaler 載入成功")
            
            # 載入元資料
            metadata_path = self.model_dir / 'model_metadata.json'
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f"✓ 元資料載入成功")
            
        except Exception as e:
            logger.error(f"模型載入失敗: {e}")
            raise

    def evaluate_on_new_data(self, X: np.ndarray, y: np.ndarray,
                             label_names: list = None) -> Dict:
        """
        在新資料上評估模型

        Args:
            X: 特徵矩陣
            y: 標籤陣列（0=normal, 1=abnormal）
            label_names: 標籤名稱列表

        Returns:
            評估結果字典
        """
        logger.info("=" * 60)
        logger.info("開始評估模型")
        logger.info("=" * 60)

        # 標準化特徵
        if self.scaler is not None:
            X = self.scaler.transform(X)
            logger.info("✓ 特徵已標準化")

        # 預測
        y_pred = self.model.predict(X)
        y_pred_proba = self.model.predict_proba(X)

        # 計算指標 - 修正：使用 average=None 來取得 support 陣列
        accuracy = accuracy_score(y, y_pred)

        # 取得每個類別的詳細指標
        precision_per_class, recall_per_class, f1_per_class, support_per_class = precision_recall_fscore_support(
            y, y_pred, average=None
        )

        # 取得 binary 平均值用於顯示
        precision, recall, f1, _ = precision_recall_fscore_support(
            y, y_pred, average='binary'
        )

        # 混淆矩陣
        cm = confusion_matrix(y, y_pred)

        # ROC-AUC
        try:
            auc = roc_auc_score(y, y_pred_proba[:, 1])
        except:
            auc = None

        # 顯示結果
        logger.info(f"\n準確率: {accuracy:.4f}")
        logger.info(f"精確率: {precision:.4f}")
        logger.info(f"召回率: {recall:.4f}")
        logger.info(f"F1 分數: {f1:.4f}")
        if auc is not None:
            logger.info(f"ROC-AUC: {auc:.4f}")

        logger.info(f"\n混淆矩陣:")
        logger.info(f"              預測 Normal  預測 Abnormal")
        logger.info(f"實際 Normal      {cm[0][0]:6d}      {cm[0][1]:6d}")
        logger.info(f"實際 Abnormal    {cm[1][0]:6d}      {cm[1][1]:6d}")

        # 詳細報告
        if label_names is None:
            label_names = ['normal', 'abnormal']

        logger.info(f"\n詳細分類報告:")
        logger.info("\n" + classification_report(y, y_pred, target_names=label_names))

        # 組織結果
        evaluation = {
            'accuracy': float(accuracy),
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1),
            'auc': float(auc) if auc is not None else None,
            'confusion_matrix': cm.tolist(),
            'support': support_per_class.tolist(),  # ✓ 使用 support_per_class
            'precision_per_class': precision_per_class.tolist(),  # 新增
            'recall_per_class': recall_per_class.tolist(),  # 新增
            'f1_per_class': f1_per_class.tolist(),  # 新增
            'predictions': {
                'y_pred': y_pred.tolist(),
                'y_pred_proba': y_pred_proba.tolist()
            }
        }

        return evaluation
    
    def cross_dataset_evaluation(self, output_dir: str = 'evaluation_results'):
        """
        跨資料集評估（從 MongoDB 載入新資料）
        
        Args:
            output_dir: 輸出目錄
        """
        logger.info("\n執行跨資料集評估...")
        
        # 載入新資料
        data_loader = DataLoader(ModelConfig.MONGODB_CONFIG)
        
        try:
            aggregation = self.metadata.get('aggregation', 'mean')
            features, labels, uuids = data_loader.load_data(aggregation=aggregation)
            
            # 編碼標籤
            label_encoder = {'normal': 0, 'abnormal': 1}
            y_encoded = np.array([label_encoder[label] for label in labels])
            
            # 評估
            evaluation = self.evaluate_on_new_data(features, y_encoded)
            
            # 儲存結果
            os.makedirs(output_dir, exist_ok=True)
            
            report_path = os.path.join(output_dir, 'cross_dataset_evaluation.json')
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(evaluation, f, indent=2, ensure_ascii=False)
            logger.info(f"\n✓ 評估報告已儲存: {report_path}")
            
            # 視覺化
            cm = np.array(evaluation['confusion_matrix'])
            cm_path = os.path.join(output_dir, 'confusion_matrix_eval.png')
            ResultVisualizer.plot_confusion_matrix(cm, cm_path)
            
            if evaluation['auc']:
                y_pred_proba = np.array(evaluation['predictions']['y_pred_proba'])
                roc_path = os.path.join(output_dir, 'roc_curve_eval.png')
                ResultVisualizer.plot_roc_curve(y_encoded, y_pred_proba, roc_path)
            
        finally:
            data_loader.close()
    
    def predict_single_record(self, analyze_uuid: str) -> Dict:
        """
        預測單一記錄
        
        Args:
            analyze_uuid: 記錄 UUID
        
        Returns:
            預測結果
        """
        # 連接 MongoDB
        data_loader = DataLoader(ModelConfig.MONGODB_CONFIG)
        
        try:
            # 查詢記錄
            record = data_loader.collection.find_one({'AnalyzeUUID': analyze_uuid})
            
            if not record:
                raise ValueError(f"找不到記錄: {analyze_uuid}")
            
            # 提取 LEAF 特徵
            analyze_features = record.get('analyze_features', [])
            leaf_features = None
            
            for step in analyze_features:
                if step.get('features_step') == 2 and step.get('features_name') == 'LEAF Features':
                    leaf_features = step.get('features_data', [])
                    break
            
            if not leaf_features:
                raise ValueError("記錄缺少 LEAF 特徵")
            
            # 提取特徵向量
            segment_features = []
            for segment in leaf_features:
                feature_vector = segment.get('feature_vector')
                if feature_vector is not None:
                    segment_features.append(feature_vector)
            
            if not segment_features:
                raise ValueError("特徵向量為空")
            
            # 聚合特徵
            segment_features = np.array(segment_features)
            aggregation = self.metadata.get('aggregation', 'mean')
            
            if aggregation == 'mean':
                aggregated_feature = np.mean(segment_features, axis=0)
            elif aggregation == 'max':
                aggregated_feature = np.max(segment_features, axis=0)
            elif aggregation == 'median':
                aggregated_feature = np.median(segment_features, axis=0)
            else:
                aggregated_feature = np.mean(segment_features, axis=0)
            
            # 重塑
            aggregated_feature = aggregated_feature.reshape(1, -1)
            
            # 標準化
            if self.scaler is not None:
                aggregated_feature = self.scaler.transform(aggregated_feature)
            
            # 預測
            prediction_class = self.model.predict(aggregated_feature)[0]
            prediction_proba = self.model.predict_proba(aggregated_feature)[0]
            
            # 解碼標籤
            label_decoder = self.metadata.get('label_decoder', {0: 'normal', 1: 'abnormal'})
            if isinstance(label_decoder, dict):
                label_decoder = {int(k) if isinstance(k, str) and k.isdigit() else k: v 
                               for k, v in label_decoder.items()}
            
            predicted_label = label_decoder.get(int(prediction_class), 'unknown')
            confidence = float(prediction_proba[int(prediction_class)])
            
            result = {
                'analyze_uuid': analyze_uuid,
                'prediction': predicted_label,
                'confidence': confidence,
                'proba_normal': float(prediction_proba[0]),
                'proba_abnormal': float(prediction_proba[1]),
                'true_label': record.get('info_features', {}).get('label', 'unknown'),
                'num_segments': len(segment_features)
            }
            
            logger.info(f"\n預測結果:")
            logger.info(f"  記錄: {analyze_uuid}")
            logger.info(f"  預測: {predicted_label} (信心度: {confidence:.3f})")
            logger.info(f"  實際標籤: {result['true_label']}")
            logger.info(f"  切片數量: {result['num_segments']}")
            
            return result
            
        finally:
            data_loader.close()
    
    def get_model_info(self) -> Dict:
        """取得模型資訊"""
        info = {
            'model_type': 'RandomForestClassifier',
            'model_dir': str(self.model_dir),
            'n_estimators': self.model.n_estimators if self.model else None,
            'max_depth': self.model.max_depth if self.model else None,
            'feature_importances': self.model.feature_importances_.tolist() if self.model else None,
            'metadata': self.metadata
        }
        return info


def main():
    """主程式"""
    print("""
╔══════════════════════════════════════════════════════════╗
║         模型評估工具 v1.0                                   ║
║                                                          ║
║  功能:                                                    ║
║  1. 載入已訓練的 RF 模型                                    ║
║  2. 在新資料上評估模型效能                                   ║
║  3. 單一記錄預測測試                                         ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # 指定模型目錄
    model_dir = ModelConfig.OUTPUT_CONFIG['model_dir']
    
    if not os.path.exists(model_dir):
        logger.error(f"模型目錄不存在: {model_dir}")
        logger.error("請先執行 train_regrassion_model.py 訓練模型")
        sys.exit(1)
    
    try:
        # 建立評估器
        evaluator = ModelEvaluator(model_dir)
        
        # 顯示模型資訊
        logger.info("\n" + "=" * 60)
        logger.info("模型資訊")
        logger.info("=" * 60)
        model_info = evaluator.get_model_info()
        logger.info(f"模型類型: {model_info['model_type']}")
        logger.info(f"樹數量: {model_info['n_estimators']}")
        logger.info(f"最大深度: {model_info['max_depth']}")
        
        # 選擇評估模式
        print("\n選擇評估模式:")
        print("  1. 跨資料集評估（從 MongoDB 載入所有資料）")
        print("  2. 單一記錄預測測試")
        print("  3. 顯示模型詳細資訊")
        print("\n請輸入選項 (1, 2 或 3): ", end='')
        
        mode = input().strip()
        
        if mode == '1':
            # 跨資料集評估
            evaluator.cross_dataset_evaluation()
            
        elif mode == '2':
            # 單一記錄預測
            print("\n請輸入記錄的 AnalyzeUUID: ", end='')
            analyze_uuid = input().strip()
            
            result = evaluator.predict_single_record(analyze_uuid)
            
            print("\n" + "=" * 60)
            print("預測結果")
            print("=" * 60)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        elif mode == '3':
            # 顯示詳細資訊
            print("\n" + "=" * 60)
            print("模型詳細資訊")
            print("=" * 60)
            print(json.dumps(model_info, indent=2, ensure_ascii=False))
            
        else:
            logger.warning("無效的選項")
        
        logger.info("\n評估完成")
        
    except KeyboardInterrupt:
        logger.info("\n\n評估被使用者中斷")
    except Exception as e:
        logger.error(f"\n評估過程發生錯誤: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
