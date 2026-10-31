import sqlite3
import os

# --- إعدادات ---
# تأكد من أن هذا المسار يطابق المسار في ملف app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'users.db')
TABLE_NAME = 'users'

# --- الأعمدة المطلوب إضافتها مع أنواع البيانات الخاصة بها ---
# 'اسم العمود': 'نوع البيانات والقيود'
COLUMNS_TO_ADD = {
    'is_frozen': 'INTEGER DEFAULT 0',
    'frozen_days_remaining': 'INTEGER DEFAULT NULL',
    'total_paid_amount': 'REAL DEFAULT 0.0'
}

def add_columns():
    """
    يتصل بقاعدة البيانات ويضيف الأعمدة المحددة إذا لم تكن موجودة بالفعل.
    """
    conn = None
    try:
        # الاتصال بقاعدة البيانات
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        print(f"Successfully connected to database: {DATABASE_PATH}")

        # جلب قائمة الأعمدة الحالية في الجدول
        cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
        # استخراج أسماء الأعمدة فقط
        existing_columns = [row[1] for row in cursor.fetchall()]
        print(f"Existing columns in '{TABLE_NAME}': {existing_columns}")

        # المرور على الأعمدة المطلوب إضافتها
        for col_name, col_type in COLUMNS_TO_ADD.items():
            if col_name not in existing_columns:
                # إذا كان العمود غير موجود، قم بإضافته
                print(f"-> Adding column '{col_name}'...")
                sql_command = f"ALTER TABLE {TABLE_NAME} ADD COLUMN {col_name} {col_type}"
                cursor.execute(sql_command)
                print(f"   Column '{col_name}' added successfully.")
            else:
                # إذا كان العمود موجوداً بالفعل، تخطاه
                print(f"-> Column '{col_name}' already exists. Skipping.")
        
        # حفظ التغييرات (مهم جداً)
        conn.commit()
        print("\nDatabase schema update process completed successfully.")

    except sqlite3.Error as e:
        print(f"\nAn error occurred: {e}")
    finally:
        # إغلاق الاتصال دائماً في النهاية
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    add_columns()