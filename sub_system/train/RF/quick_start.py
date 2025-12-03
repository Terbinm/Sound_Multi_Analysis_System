# quick_start.py - 快速訓練與部署腳本

import os
import sys
import json
import shutil
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QuickStart:
    """快速啟動助手"""

    def __init__(self):
        """初始化"""
        self.project_root = Path.cwd()

        # 修正：檢查當前目錄是否在 RF 資料夾中
        if self.project_root.name == 'RF':
            # 如果在 RF 資料夾，需要向上找到專案根目錄
            self.project_root = self.project_root.parent.parent.parent
            logger.info(f"偵測到在 RF 目錄中，專案根目錄: {self.project_root}")

        self.model_dir = Path.cwd() / 'models'  # 模型目錄在當前位置
        self.report_dir = Path.cwd() / 'training_reports'  # 報告目錄在當前位置

        # 分析服務目錄使用絕對路徑
        self.analysis_service_dir = self.project_root / 'a_sub_system' / 'analysis_service'

        logger.info(f"專案根目錄: {self.project_root}")
        logger.info(f"模型目錄: {self.model_dir}")
        logger.info(f"分析服務目錄: {self.analysis_service_dir}")

    def check_environment(self) -> bool:
        """檢查環境"""
        logger.info("=" * 60)
        logger.info("步驟 1: 檢查環境")
        logger.info("=" * 60)

        errors = []

        # 檢查必要套件
        try:
            import sklearn
            logger.info("✓ scikit-learn 已安裝")
        except ImportError:
            errors.append("scikit-learn 未安裝")
        except Exception as e:
            logger.warning(f"scikit-learn 載入警告: {e}")
            logger.info("✓ scikit-learn 已安裝（但可能有配置問題）")

        try:
            import matplotlib
            matplotlib.use('Agg')  # 使用非互動式後端，避免 GUI 相關問題
            logger.info("✓ matplotlib 已安裝")
        except ImportError:
            errors.append("matplotlib 未安裝")
        except Exception as e:
            logger.warning(f"matplotlib 載入警告: {e}")
            logger.info("✓ matplotlib 已安裝（但可能有配置問題）")

        try:
            import seaborn
            logger.info("✓ seaborn 已安裝")
        except ImportError:
            errors.append("seaborn 未安裝")
        except Exception as e:
            logger.warning(f"seaborn 載入警告: {e}")
            logger.info("✓ seaborn 已安裝（但可能有配置問題）")

        try:
            from pymongo import MongoClient
            logger.info("✓ pymongo 已安裝")
        except ImportError:
            errors.append("pymongo 未安裝")
        except Exception as e:
            logger.warning(f"pymongo 載入警告: {e}")
            logger.info("✓ pymongo 已安裝（但可能有配置問題）")

        # 檢查必要檔案（在當前目錄）
        required_files = [
            'train_rf_model.py',
            'rf_evaluate_model.py',
            'step3_classifier_updated.py'
        ]

        for file in required_files:
            if Path(file).exists():
                logger.info(f"✓ {file} 存在")
            else:
                errors.append(f"{file} 不存在")

        if errors:
            logger.error("\n環境檢查失敗:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.info("\n✓ 環境檢查通過")
        return True

    def check_data(self) -> dict:
        """檢查訓練資料"""
        logger.info("\n" + "=" * 60)
        logger.info("步驟 2: 檢查訓練資料")
        logger.info("=" * 60)

        try:
            from pymongo import MongoClient

            # 連接 MongoDB
            client = MongoClient("mongodb://web_ui:hod2iddfsgsrl@localhost:27025/admin")
            db = client['web_db']
            collection = db['recordings']

            # 查詢資料
            query = {
                'current_step': 4,
                'analysis_status': 'completed',
                'info_features.label': {'$exists': True, '$ne': 'unknown'}
            }
            abnormal_labels = [
                # 'abnormal',
                'horizontal_misalignment',
                'vertical_misalignment',
                'underhang',
                'overhang',
                'imbalance',
            ]

            total_count = total_count = collection.count_documents({**query, 'info_features.label': {'$in': ['normal',    *abnormal_labels]}})
            normal_count = collection.count_documents({**query, 'info_features.label': 'normal'})
            # abnormal_count = collection.count_documents({**query, 'info_features.label': 'abnormal'})

            abnormal_count = collection.count_documents({
                **query,
                'info_features.label': {'$in': abnormal_labels},
            })

            logger.info(f"總資料量: {total_count} 筆")
            logger.info(f"  - Normal: {normal_count} 筆 ({normal_count / total_count * 100:.1f}%)")
            logger.info(f"  - Abnormal: {abnormal_count} 筆 ({abnormal_count / total_count * 100:.1f}%)")

            # 判斷資料是否足夠
            if total_count < 50:
                logger.warning("\n⚠️ 訓練資料不足 (建議至少 200 筆)")
                logger.warning("請使用 batch_upload 工具上傳更多資料")
                return {'sufficient': False, 'count': total_count}
            elif total_count < 200:
                logger.warning("\n⚠️ 訓練資料偏少 (建議至少 200 筆)")
                logger.warning("模型效能可能不佳,建議上傳更多資料")
            else:
                logger.info("\n✓ 訓練資料充足")

            # 檢查類別平衡
            if normal_count > 0 and abnormal_count > 0:
                ratio = max(normal_count, abnormal_count) / min(normal_count, abnormal_count)
                if ratio > 3:
                    logger.warning(f"\n⚠️ 類別不平衡 (比例: {ratio:.1f}:1)")
                    logger.warning("建議增加少數類別的樣本數")

            client.close()

            return {
                'sufficient': total_count >= 50,
                'count': total_count,
                'normal': normal_count,
                'abnormal': abnormal_count
            }

        except Exception as e:
            logger.error(f"檢查資料失敗: {e}")
            return {'sufficient': False, 'count': 0}

    def train_model(self) -> bool:
        """訓練模型"""
        logger.info("\n" + "=" * 60)
        logger.info("步驟 3: 訓練模型")
        logger.info("=" * 60)

        try:
            # 執行訓練腳本
            import train_rf_model
            train_rf_model.main()

            # 檢查輸出
            if (self.model_dir / 'rf_classifier.pkl').exists():
                logger.info("\n✓ 模型訓練成功")
                return True
            else:
                logger.error("\n✗ 模型檔案未生成")
                return False

        except KeyboardInterrupt:
            logger.info("\n訓練被使用者中斷")
            return False
        except Exception as e:
            logger.error(f"\n訓練失敗: {e}")
            return False

    def evaluate_model(self) -> bool:
        """評估模型"""
        logger.info("\n" + "=" * 60)
        logger.info("步驟 4: 評估模型")
        logger.info("=" * 60)

        try:
            from rf_evaluate_model import ModelEvaluator

            evaluator = ModelEvaluator(str(self.model_dir))

            # 執行跨資料集評估
            logger.info("\n執行跨資料集評估...")
            evaluator.cross_dataset_evaluation(output_dir='evaluation_results')

            # 讀取評估結果
            eval_report_path = Path('evaluation_results') / 'cross_dataset_evaluation.json'
            if eval_report_path.exists():
                with open(eval_report_path, 'r', encoding='utf-8') as f:
                    eval_result = json.load(f)

                logger.info("\n模型效能:")
                logger.info(f"  準確率: {eval_result['accuracy']:.4f}")
                logger.info(f"  精確率: {eval_result['precision']:.4f}")
                logger.info(f"  召回率: {eval_result['recall']:.4f}")
                logger.info(f"  F1分數: {eval_result['f1_score']:.4f}")

                # 判斷是否可以部署
                if eval_result['accuracy'] >= 0.7:
                    logger.info("\n✓ 模型效能良好,可以部署")
                    return True
                else:
                    logger.warning("\n⚠️ 模型效能不佳,建議:")
                    logger.warning("  1. 增加訓練資料")
                    logger.warning("  2. 調整模型參數")
                    logger.warning("  3. 檢查資料品質")

                    print("\n是否仍要部署? (y/n): ", end='')
                    confirm = input().strip().lower()
                    return confirm == 'y'
            else:
                logger.warning("無法讀取評估報告")
                return False

        except Exception as e:
            logger.error(f"\n評估失敗: {e}")
            return False

    def deploy_model(self) -> bool:
        """部署模型"""
        logger.info("\n" + "=" * 60)
        logger.info("步驟 5: 部署模型")
        logger.info("=" * 60)

        try:
            # 檢查分析服務目錄是否存在
            if not self.analysis_service_dir.exists():
                logger.error(f"分析服務目錄不存在: {self.analysis_service_dir}")
                logger.error("請確認專案結構是否正確")
                return False

            processors_dir = self.analysis_service_dir / 'processors'
            if not processors_dir.exists():
                logger.error(f"processors 目錄不存在: {processors_dir}")
                return False

            # 1. 備份原始分類器
            original_classifier = processors_dir / 'step3_classifier.py'
            backup_classifier = processors_dir / 'step3_classifier_backup.py'

            logger.info(f"原始分類器路徑: {original_classifier}")

            if not original_classifier.exists():
                logger.warning(f"原始分類器不存在: {original_classifier}")
                logger.warning("將直接建立新的分類器")
            elif not backup_classifier.exists():
                shutil.copy(original_classifier, backup_classifier)
                logger.info("✓ 原始分類器已備份")
            else:
                logger.info("✓ 備份檔案已存在，跳過備份")

            # 2. 替換分類器
            new_classifier = Path.cwd() / 'step3_classifier_updated.py'

            if not new_classifier.exists():
                logger.error(f"新分類器檔案不存在: {new_classifier}")
                return False

            shutil.copy(new_classifier, original_classifier)
            logger.info("✓ 分類器已更新")

            # 3. 更新配置檔案
            config_path = self.analysis_service_dir / 'config.py'

            if config_path.exists():
                # 讀取配置
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_content = f.read()

                # 取得模型目錄的絕對路徑
                model_path_abs = str(self.model_dir.absolute()).replace('\\', '/')

                logger.info(f"設定模型路徑: {model_path_abs}")

                # 更新配置
                import re

                # 更新 method
                config_content = re.sub(
                    r"'method':\s*'random'",
                    "'method': 'rf_model'",
                    config_content
                )

                # 更新或添加 model_path
                if "'model_path':" in config_content:
                    config_content = re.sub(
                        r"'model_path':\s*['\"][^'\"]*['\"]",
                        f"'model_path': '{model_path_abs}'",
                        config_content
                    )
                else:
                    # 如果不存在，在 CLASSIFICATION_CONFIG 中添加
                    config_content = re.sub(
                        r"(CLASSIFICATION_CONFIG\s*=\s*\{[^}]*'classes':[^,]+,)",
                        f"\\1\n    'model_path': '{model_path_abs}',",
                        config_content
                    )

                # 寫回配置
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(config_content)

                logger.info("✓ 配置檔案已更新")
                logger.info(f"  method: rf_model")
                logger.info(f"  model_path: {model_path_abs}")
            else:
                logger.warning(f"配置檔案不存在: {config_path}")
                logger.warning("請手動更新配置")

            logger.info("\n✓ 模型部署完成")
            logger.info("\n請重啟分析服務以使用新模型:")
            logger.info(f"  cd {self.analysis_service_dir}")
            logger.info("  python main.py")

            return True

        except Exception as e:
            logger.error(f"\n部署失敗: {e}", exc_info=True)
            return False

    def run(self):
        """執行完整流程"""
        print("""
╔══════════════════════════════════════════════════════════╗
║         RF 模型快速訓練與部署工具 v1.0                       ║
║                                                          ║
║  本工具將自動完成:                                          ║
║  1. 環境檢查                                               ║
║  2. 資料檢查                                               ║
║  3. 模型訓練                                               ║
║  4. 模型評估                                               ║
║  5. 模型部署                                               ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
        """)

        # 步驟 1: 環境檢查
        if not self.check_environment():
            logger.error("\n環境檢查失敗,請先安裝必要套件:")
            logger.error("  pip install scikit-learn matplotlib seaborn --break-system-packages")
            return

        # 步驟 2: 資料檢查
        data_info = self.check_data()
        if not data_info['sufficient']:
            logger.error("\n訓練資料不足,無法繼續")
            logger.error("請使用 batch_upload 工具上傳更多已標記的音頻資料")
            return

        # 確認開始訓練
        print("\n" + "=" * 60)
        print("準備開始訓練模型")
        print("=" * 60)
        print(f"訓練資料: {data_info['count']} 筆")
        print(f"  - Normal: {data_info['normal']} 筆")
        print(f"  - Abnormal: {data_info['abnormal']} 筆")
        print("\n是否開始訓練? (y/n): ", end='')

        confirm = input().strip().lower()
        if confirm != 'y':
            logger.info("已取消")
            return

        # 步驟 3: 訓練模型
        if not self.train_model():
            logger.error("\n訓練失敗,流程中止")
            return

        # 步驟 4: 評估模型
        if not self.evaluate_model():
            logger.warning("\n評估未通過,流程中止")
            return

        # 步驟 5: 部署模型
        print("\n" + "=" * 60)
        print("是否部署模型到分析服務? (y/n): ", end='')
        confirm = input().strip().lower()

        if confirm == 'y':
            if self.deploy_model():
                logger.info("\n" + "=" * 60)
                logger.info("✓ 所有步驟完成!")
                logger.info("=" * 60)
                logger.info("\n下一步:")
                logger.info("  1. 重啟分析服務")
                logger.info("  2. 上傳測試音頻驗證模型")
                logger.info("  3. 查看訓練報告: training_reports/")
                logger.info("  4. 查看評估報告: evaluation_results/")
            else:
                logger.error("\n部署失敗")
        else:
            logger.info("\n已跳過部署,可稍後手動部署")
            logger.info("詳見 RF_MODEL_GUIDE.md")


def main():
    """主程式"""
    quick_start = QuickStart()

    try:
        quick_start.run()
    except KeyboardInterrupt:
        logger.info("\n\n流程被使用者中斷")
    except Exception as e:
        logger.error(f"\n發生錯誤: {e}", exc_info=True)


if __name__ == '__main__':
    main()