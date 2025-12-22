# test_env_db.py（放在ArkDataKit目录）
import os
import mysql.connector
from mysql.connector import Error

# 1. 强制加载.env（绝对路径）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# 2. 读取配置并打印
config = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "auth_plugin": "mysql_native_password"
}

print("📌 测试配置读取：")
print(f"  - host: {config['host']}")
print(f"  - port: {config['port']}")
print(f"  - user: {config['user']}")
print(f"  - password: {'*'*len(config['password'])}")

# 3. 测试数据库连接
try:
    conn = mysql.connector.connect(**config)
    if conn.is_connected():
        print("\n✅ 数据库连接成功！")
        conn.close()
    else:
        print("\n❌ 数据库连接失败（未连接）")
except Error as e:
    print(f"\n❌ 连接失败：{e.errno} - {e.msg}")
except Exception as e:
    print(f"\n❌ 未知错误：{str(e)}")