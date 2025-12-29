"""
初始化管理員帳戶腳本

使用方法:
    python init_admin.py

或自訂使用者名稱與密碼:
    python init_admin.py --username admin --password admin123 --email admin@example.com
    python init_admin.py --username staging --password admin123 --email admin@example.com

"""
import sys
import os
import argparse
import getpass
from flask_bcrypt import generate_password_hash
from models.user import User
from config import get_config
import logging

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_admin_user(username=None, email=None, password=None):
    """
    建立管理員使用者（冪等操作）

    Args:
        username: 使用者名稱（若為 None 則從環境變數讀取）
        email: 電子郵件（若為 None 則從環境變數讀取）
        password: 密碼（若為 None 則互動式輸入）

    Returns:
        bool: 是否建立成功（已存在視為成功）
    """
    try:
        # 從 config 讀取預設值
        config = get_config()
        if username is None:
            username = os.getenv('INIT_ADMIN_USERNAME')
            if not username:
                raise ValueError("未設定 INIT_ADMIN_USERNAME 環境變數")
        if email is None:
            email = os.getenv('INIT_ADMIN_EMAIL')
            if not email:
                raise ValueError("未設定 INIT_ADMIN_EMAIL 環境變數")
        
        # 檢查使用者是否已存在（冪等性：已存在則跳過）
        existing_user = User.find_by_username(username)
        if existing_user:
            logger.info(f"✓ 使用者 '{username}' 已存在，跳過建立")
            return True

        # 檢查電子郵件是否已被使用（但用戶名不同）
        existing_email = User.find_by_email(email)
        if existing_email:
            logger.warning(f"電子郵件 '{email}' 已被其他使用者使用，跳過建立")
            return True

        # 取得密碼
        if password is None:
            password = getpass.getpass('請輸入管理員密碼: ')
            password_confirm = getpass.getpass('請確認密碼: ')

            if password != password_confirm:
                logger.error("兩次密碼輸入不一致")
                return False

        if len(password) < 6:
            logger.error("密碼長度至少需 6 個字元")
            return False

        # 生成密碼雜湊
        password_hash = generate_password_hash(password).decode('utf-8')

        # 建立管理員使用者
        user = User.create(
            username=username,
            email=email,
            password_hash=password_hash,
            role=User.ROLE_ADMIN
        )

        if user:
            logger.info("✓ 管理員使用者建立成功")
            logger.info(f"  使用者名稱: {username}")
            logger.info(f"  電子郵件: {email}")
            logger.info("  角色: 管理員")
            logger.info("\n請使用以下資訊登入:")
            logger.info(f"  URL: http://{config.HOST}:{config.PORT}/auth/login")
            logger.info(f"  使用者名稱: {username}")
            return True
        else:
            logger.error("建立管理員使用者失敗")
            return False

    except Exception as e:
        logger.error(f"建立管理員使用者時發生錯誤: {str(e)}", exc_info=True)
        return False


def create_indexes():
    """建立必要的資料庫索引"""
    try:
        logger.info("建立資料庫索引...")
        User.create_indexes()
        logger.info("✓ 資料庫索引建立成功")
        return True
    except Exception as e:
        logger.error(f"建立資料庫索引失敗: {str(e)}")
        return False


def main():
    """主函式"""
    # 從環境變數讀取預設值
    default_username = os.getenv('INIT_ADMIN_USERNAME', 'admin')
    default_email = os.getenv('INIT_ADMIN_EMAIL', 'admin@example.com')
    default_password = os.getenv('INIT_ADMIN_PASSWORD')  # 不建議在 .env 設定密碼
    
    parser = argparse.ArgumentParser(description='初始化管理員帳戶')
    parser.add_argument('--username', type=str, default=default_username,
                      help=f'管理員使用者名稱（預設: {default_username}）')
    parser.add_argument('--email', type=str, default=default_email,
                      help=f'管理員電子郵件（預設: {default_email}）')
    parser.add_argument('--password', type=str, default=default_password,
                      help='管理員密碼（未提供則互動式輸入）')
    parser.add_argument('--skip-indexes', action='store_true',
                      help='略過建立資料庫索引')

    args = parser.parse_args()

    print("=" * 60)
    print("State Management System - 初始化管理員帳戶")
    print("=" * 60)
    print()

    # 建立資料庫索引
    if not args.skip_indexes:
        if not create_indexes():
            logger.warning("索引建立失敗，但將繼續建立管理員帳戶")
        print()

    # 建立管理員使用者
    success = create_admin_user(
        username=args.username,
        email=args.email,
        password=args.password
    )

    print()
    print("=" * 60)

    if success:
        print("✓ 初始化完成！")
        return 0
    else:
        print("✗ 初始化失敗")
        return 1


if __name__ == '__main__':
    sys.exit(main())
