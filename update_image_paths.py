# -*- coding: utf-8 -*-
"""
更新数据库中的图片路径
将旧路径改为新路径
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text

# 数据库连接
DATABASE_URL = "postgresql://postgres:mm@localhost:5432/defect_detection"

def main():
    print("=" * 60)
    print("更新图片路径")
    print("=" * 60)

    engine = create_engine(DATABASE_URL)
    conn = engine.connect()

    try:
        # 1. 查看当前数据
        print("\n[1/3] 查看当前数据库中的图片路径...")
        result = conn.execute(text("SELECT id, filename, path, folder FROM image_database LIMIT 5;"))
        rows = result.fetchall()

        if rows:
            print("\n当前路径示例:")
            for row in rows:
                print(f"  ID: {row[0]}, Path: {row[2]}")
        else:
            print("  数据库中没有图片记录")
            conn.close()
            return

        # 2. 统计需要更新的记录
        print("\n[2/3] 统计需要更新的记录...")
        old_path = r"G:\ShuangChuang\ShuangC\datasets\检测\HighRPD\images"

        # 直接查询所有记录进行统计
        result = conn.execute(text("SELECT COUNT(*) FROM image_database"))
        total_count = result.fetchone()[0]

        result = conn.execute(text("SELECT COUNT(*) FROM image_database WHERE path LIKE '%datasets%HighRPD%'"))
        count = result.fetchone()[0]

        print(f"  数据库总记录数: {total_count}")
        print(f"  找到 {count} 条使用旧路径的记录")

        if count == 0:
            print("  ⚠️ 没有找到旧路径记录,但数据库中有记录")
            print("  请检查路径格式")
            conn.close()
            return

        # 3. 确认更新
        print(f"\n⚠️  即将更新 {count} 条记录")
        print(f"  旧路径: {old_path}")
        print(f"  新路径: G:\\ShuangChuang\\ShuangC\\backend\\uploads\\images")
        confirm = input("\n确认更新? (输入 yes 继续): ")

        if confirm.lower() != 'yes':
            print("已取消")
            conn.close()
            return

        # 4. 执行更新
        print("\n[3/3] 更新路径...")
        old_path = r"G:\ShuangChuang\ShuangC\datasets\检测\HighRPD\images"
        new_path = r"G:\ShuangChuang\ShuangC\backend\uploads\images"

        # 使用 PostgreSQL 的 REPLACE 函数
        result = conn.execute(text("""
            UPDATE image_database
            SET path = REPLACE(path, :old_path, :new_path)
            WHERE path LIKE '%datasets%HighRPD%'
            RETURNING id
        """), {
            "old_path": old_path,
            "new_path": new_path
        })

        updated_count = len(result.fetchall())
        conn.commit()
        print(f"  ✅ 成功更新 {updated_count} 条记录")

        # 5. 验证
        print("\n验证更新结果...")
        result = conn.execute(text("SELECT id, filename, path FROM image_database LIMIT 3;"))
        rows = result.fetchall()
        print("\n更新后的路径示例:")
        for row in rows:
            print(f"  ID: {row[0]}, Path: {row[2]}")

        print("\n" + "=" * 60)
        print("✅ 路径更新完成!")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        engine.dispose()

if __name__ == "__main__":
    main()
    print("\n按回车键退出...")
    input()
