import sqlite3

db_path = "data/zhiban.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查看当前字段
cursor.execute("PRAGMA table_info(generation_jobs)")
columns = [row[1] for row in cursor.fetchall()]

print("当前字段:")
print(columns)


# 添加 model_used
if "model_used" not in columns:
    cursor.execute("""
    ALTER TABLE generation_jobs 
    ADD COLUMN model_used VARCHAR(100)
    """)
    print("Added model_used")


# 添加 strategy_used
if "strategy_used" not in columns:
    cursor.execute("""
    ALTER TABLE generation_jobs 
    ADD COLUMN strategy_used VARCHAR(100)
    """)
    print("Added strategy_used")


conn.commit()


# 再次检查
cursor.execute("PRAGMA table_info(generation_jobs)")
columns = cursor.fetchall()

print("\n修改后字段:")
for col in columns:
    print(col)


conn.close()

print("\nMigration success!")