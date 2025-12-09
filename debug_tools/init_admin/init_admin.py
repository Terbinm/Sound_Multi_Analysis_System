"""
獨立的管理員帳戶初始化工具

這是一個獨立的工具，可以連接到任何指定的 MongoDB 資料庫來建立管理員使用者。
不依賴於核心系統的配置，允許靈活配置資料庫連接參數。

使用方法:
    python init_admin.py

此工具將提供互動式介面來設定：
- MongoDB 連接資訊
- 管理員帳戶資訊
"""
import sys
import os
import getpass
import logging
from typing import Optional, Dict, Any
from datetime import datetime

try:
    from pymongo import MongoClient
    from flask_bcrypt import generate_password_hash
except ImportError as e:
    print(f"缺少必要的套件: {e}")
    print("請執行: pip install pymongo flask-bcrypt")
    sys.exit(1)

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseConfig:
    """資料庫配置類"""
    
    def __init__(self, host: str = 'localhost', port: int = 27017, 
                 username: str = '', password: str = '', 
                 database: str = 'web_db', auth_source: str = 'admin'):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.auth_source = auth_source
    
    def get_uri(self) -> str:
        """獲取 MongoDB 連接 URI"""
        if self.username and self.password:
            return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}?authSource={self.auth_source}"
        else:
            return f"mongodb://{self.host}:{self.port}/{self.database}"


class UserManager:
    """使用者管理類"""
    
    ROLE_ADMIN = 'admin'
    ROLE_USER = 'user'
    VALID_ROLES = [ROLE_ADMIN, ROLE_USER]
    
    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self._client = None
        self._db = None
        self._connect()
    
    def _connect(self):
        """建立資料庫連接"""
        try:
            uri = self.db_config.get_uri()
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            
            # 測試連接
            self._client.admin.command('ping')
            self._db = self._client[self.db_config.database]
            
            logger.info(f"✓ 成功連接到 MongoDB: {self.db_config.host}:{self.db_config.port}/{self.db_config.database}")
            
        except Exception as e:
            logger.error(f"連接 MongoDB 失敗: {str(e)}")
            raise
    
    def get_users_collection(self):
        """獲取使用者集合"""
        return self._db.users
    
    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根據使用者名稱查找使用者"""
        try:
            collection = self.get_users_collection()
            return collection.find_one({'username': username})
        except Exception as e:
            logger.error(f"查找使用者失敗: {str(e)}")
            return None
    
    def find_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根據電子郵件查找使用者"""
        try:
            collection = self.get_users_collection()
            return collection.find_one({'email': email})
        except Exception as e:
            logger.error(f"查找使用者失敗: {str(e)}")
            return None
    
    def create_user(self, username: str, email: str, password_hash: str, 
                   role: str = ROLE_USER) -> bool:
        """建立新使用者"""
        try:
            # 驗證角色
            if role not in self.VALID_ROLES:
                logger.error(f"無效的角色: {role}")
                return False
            
            # 檢查使用者名稱是否已存在
            if self.find_by_username(username):
                logger.error(f"使用者名稱已存在: {username}")
                return False
            
            # 檢查電子郵件是否已存在
            if self.find_by_email(email):
                logger.error(f"電子郵件已存在: {email}")
                return False
            
            # 建立使用者文檔
            now = datetime.utcnow()
            user_data = {
                'username': username,
                'email': email,
                'password_hash': password_hash,
                'role': role,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
                'last_login': None
            }
            
            collection = self.get_users_collection()
            result = collection.insert_one(user_data)
            
            if result.inserted_id:
                logger.info(f"✓ 使用者建立成功: {username}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"建立使用者失敗: {str(e)}")
            return False
    
    def create_indexes(self):
        """建立必要的資料庫索引"""
        try:
            collection = self.get_users_collection()
            
            # 使用者名稱唯一索引
            collection.create_index('username', unique=True)
            
            # 電子郵件唯一索引
            collection.create_index('email', unique=True)
            
            # 角色索引
            collection.create_index('role')
            
            # 啟用狀態索引
            collection.create_index('is_active')
            
            logger.info("✓ 資料庫索引建立成功")
            return True
        except Exception as e:
            logger.error(f"建立資料庫索引失敗: {str(e)}")
            return False
    
    def close(self):
        """關閉資料庫連接"""
        if self._client:
            self._client.close()


def get_database_config() -> DatabaseConfig:
    """互動式獲取資料庫配置"""
    print("\n" + "=" * 60)
    print("MongoDB 資料庫連接設定")
    print("=" * 60)
    print()
    
    # 預設值（針對系統的常見配置）
    default_configs = {
        '1': {
            'name': '本地開發環境 (預設)',
            'host': 'localhost',
            'port': 27017,
            'username': '',
            'password': '',
            'database': 'web_db',
            'auth_source': 'admin'
        },
        '2': {
            'name': '本地核心服務',
            'host': 'localhost',
            'port': 55101,
            'username': 'web_ui',
            'password': 'hod2iddfsgsrl',
            'database': 'web_db',
            'auth_source': 'admin'
        },
        '3': {
            'name': '自訂設定',
            'host': '',
            'port': 27017,
            'username': '',
            'password': '',
            'database': 'web_db',
            'auth_source': 'admin'
        }
    }
    
    print("請選擇資料庫配置:")
    for key, config in default_configs.items():
        print(f"  {key}. {config['name']}")
    print()
    
    while True:
        choice = input("請選擇 (1-3): ").strip()
        if choice in default_configs:
            selected_config = default_configs[choice].copy()
            break
        print("無效的選擇，請重新輸入")
    
    if choice == '3':  # 自訂設定
        print("\n請輸入 MongoDB 連接資訊:")
        selected_config['host'] = input(f"主機地址 [{selected_config['host']}]: ").strip() or selected_config['host']
        
        port_input = input(f"連接埠 [{selected_config['port']}]: ").strip()
        if port_input:
            try:
                selected_config['port'] = int(port_input)
            except ValueError:
                print("無效的連接埠，使用預設值")
        
        selected_config['database'] = input(f"資料庫名稱 [{selected_config['database']}]: ").strip() or selected_config['database']
        selected_config['username'] = input(f"使用者名稱 [{selected_config['username']}]: ").strip() or selected_config['username']
        
        if selected_config['username']:
            selected_config['password'] = getpass.getpass("密碼: ") or selected_config['password']
            selected_config['auth_source'] = input(f"認證資料庫 [{selected_config['auth_source']}]: ").strip() or selected_config['auth_source']
    
    return DatabaseConfig(
        host=selected_config['host'],
        port=selected_config['port'],
        username=selected_config['username'],
        password=selected_config['password'],
        database=selected_config['database'],
        auth_source=selected_config['auth_source']
    )


def get_admin_info() -> tuple:
    """互動式獲取管理員資訊"""
    print("\n" + "=" * 60)
    print("管理員帳戶設定")
    print("=" * 60)
    print()
    
    # 獲取使用者名稱
    while True:
        username = input("管理員使用者名稱 [admin]: ").strip() or 'admin'
        if len(username) >= 3:
            break
        print("使用者名稱長度至少需 3 個字元")
    
    # 獲取電子郵件
    while True:
        email = input("管理員電子郵件 [admin@example.com]: ").strip() or 'admin@example.com'
        if '@' in email and '.' in email:
            break
        print("請輸入有效的電子郵件地址")
    
    # 獲取密碼
    while True:
        password = getpass.getpass("管理員密碼 (至少 6 個字元): ")
        if len(password) >= 6:
            password_confirm = getpass.getpass("確認密碼: ")
            if password == password_confirm:
                break
            else:
                print("兩次密碼輸入不一致，請重新輸入")
        else:
            print("密碼長度至少需 6 個字元")
    
    return username, email, password


def main():
    """主函式"""
    print("=" * 60)
    print("Sound Multi Analysis System")
    print("管理員帳戶初始化工具 (獨立版)")
    print("=" * 60)
    print()
    print("此工具可以連接到任何 MongoDB 資料庫並建立管理員使用者")
    print("適用於開發、測試和生產環境的初始化作業")
    print()
    
    try:
        # 獲取資料庫配置
        db_config = get_database_config()
        
        # 獲取管理員資訊
        username, email, password = get_admin_info()
        
        print("\n" + "=" * 60)
        print("開始初始化...")
        print("=" * 60)
        
        # 建立使用者管理器
        user_manager = UserManager(db_config)
        
        try:
            # 建立資料庫索引
            print("\n正在建立資料庫索引...")
            if not user_manager.create_indexes():
                logger.warning("索引建立失敗，但將繼續建立管理員帳戶")
            
            # 生成密碼雜湊
            print("正在生成密碼雜湊...")
            password_hash = generate_password_hash(password).decode('utf-8')
            
            # 建立管理員使用者
            print("正在建立管理員帳戶...")
            success = user_manager.create_user(
                username=username,
                email=email,
                password_hash=password_hash,
                role=UserManager.ROLE_ADMIN
            )
            
            print("\n" + "=" * 60)
            
            if success:
                print("✓ 初始化完成！")
                print()
                print("管理員帳戶資訊:")
                print(f"  使用者名稱: {username}")
                print(f"  電子郵件: {email}")
                print("  角色: 管理員")
                print()
                print("資料庫資訊:")
                print(f"  主機: {db_config.host}:{db_config.port}")
                print(f"  資料庫: {db_config.database}")
                print()
                print("您可以使用上述資訊登入管理介面")
                return 0
            else:
                print("✗ 初始化失敗")
                return 1
                
        finally:
            # 確保關閉資料庫連接
            user_manager.close()
            
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        return 1
    except Exception as e:
        logger.error(f"初始化過程發生錯誤: {str(e)}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())