import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "answers.db"


DEFAULT_PYTHON_CHAPTERS = [
    {"id": 511001, "seq": 1, "name": "مقدمة", "test_type": "review", "question_count": 6},
    {"id": 511002, "seq": 2, "name": "الحسابات والنصوص", "test_type": "review", "question_count": 9},
    {"id": 511003, "seq": 3, "name": "المتغيرات", "test_type": "review", "question_count": 6},
    {"id": 511004, "seq": 4, "name": "مراجعة الفهم 1", "test_type": "test", "question_count": 8},
    {"id": 511005, "seq": 5, "name": "جملة if", "test_type": "review", "question_count": 5},
    {"id": 511006, "seq": 6, "name": "جمل if - else", "test_type": "review", "question_count": 5},
    {"id": 511007, "seq": 7, "name": "جمل elif", "test_type": "review", "question_count": 5},
    {"id": 511008, "seq": 8, "name": "مراجعة الفهم 2", "test_type": "test", "question_count": 7},
    {"id": 511009, "seq": 9, "name": "العامل المنطقي", "test_type": "review", "question_count": 5},
    {"id": 511010, "seq": 10, "name": "العملية التكرارية", "test_type": "review", "question_count": 5},
    {"id": 511011, "seq": 11, "name": "مراجعة الفهم 3", "test_type": "test", "question_count": 6},
    {"id": 511012, "seq": 12, "name": "الدالة (1)", "test_type": "review", "question_count": 5},
    {"id": 511013, "seq": 13, "name": "الدالة (2)", "test_type": "review", "question_count": 5},
    {"id": 511014, "seq": 14, "name": "مراجعة الفهم 4", "test_type": "test", "question_count": 6},
    {"id": 511015, "seq": 15, "name": "المصفوفة (1)", "test_type": "review", "question_count": 5},
    {"id": 511016, "seq": 16, "name": "المصفوفة (2)", "test_type": "review", "question_count": 5},
    {"id": 511017, "seq": 17, "name": "مراجعة الفهم 5", "test_type": "test", "question_count": 6},
    {"id": 511018, "seq": 18, "name": "bool", "test_type": "review", "question_count": 5},
    {"id": 511019, "seq": 19, "name": "الدوال (3)", "test_type": "review", "question_count": 5},
    {"id": 511020, "seq": 20, "name": "مراجعة الفهم 6", "test_type": "test", "question_count": 6},
    {"id": 511021, "seq": 21, "name": "مراجعة الفهم 7", "test_type": "test", "question_count": 6},
    {"id": 511022, "seq": 22, "name": "مراجعة الفهم 8", "test_type": "test", "question_count": 6},
    {"id": 511023, "seq": 23, "name": "جملة for والمصفوفة", "test_type": "review", "question_count": 5},
    {"id": 511024, "seq": 24, "name": "مراجعة الفهم 9", "test_type": "test", "question_count": 6},
    {"id": 511025, "seq": 25, "name": "مراجعة الفهم 10", "test_type": "test", "question_count": 6},
]

DEFAULT_JS_CHAPTERS = [
    {
        "id": 90000 + i,
        "seq": i,
        "name": (
            "المخطط الانسيابي" if i == 32 else
            "مراجعة المتغيرات والعمليات" if i == 31 else
            "مراجعة الفهم" if (i % 4 == 0 or i == 33) else
            f"الفصل {i}"
        ),
        "test_type": "test" if (i % 4 == 0 or i == 33) else "review",
        "question_count": 5
    }
    for i in range(1, 41)
]


def normalize_arabic_text(text: str) -> str:
    """تنظيف وتوحيد نصوص اللغة العربية لتسهيل البحث الدقيق والمطابقة العادلة"""
    if not text:
        return ""
    import re
    # Remove HTML entities & tashkeel
    t = str(text).replace("&#34;", '"').replace("&quot;", '"').replace("'", "")
    t = re.sub(r'[\u064B-\u0652\u0670]', '', t)
    # Normalize alef forms
    t = re.sub(r'[إأآٱ]', 'ا', t)
    # Normalize yaa forms
    t = re.sub(r'[ى]', 'ي', t)
    # Normalize taa marbuta
    t = re.sub(r'[ة]', 'ه', t)
    # Remove punctuation
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split()).strip().lower()


class AnswersDB:
    """
    قاعدة بيانات محلية (SQLite) لحفظ وتخزين جميع الأسئلة والإجابات النموذجية لمنصة كيريو.
    تتيح للتطبيق بناء بنك إجابات دائم، بحيث يتم حل أي سؤال معروف مسبقاً من المحاولة الأولى بنسبة 100%.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self.firebase = None
        try:
            from config import Config
            from solver.firebase_db import FirebaseManager
            self.firebase = FirebaseManager(cred_path=getattr(Config, "FIREBASE_CREDENTIALS_PATH", None))
        except Exception as e:
            logger.warning(f"تعذر تهيئة FirebaseManager في AnswersDB: {e}")

        self.seed_default_chapters()
        self.seed_spx_default_questions()
        py_cnt = len(self.get_all_chapters("python_short_ar"))
        js_cnt = len(self.get_all_chapters("javascript_ar"))
        fin_cnt = self.get_financial_questions_count()
        total_ans = self.get_total_count()
        logger.info(
            f"✅ تم تحميل وتهيئة قاعدة البيانات المحلية (SQLite) بنجاح "
            f"[بايثون: {py_cnt} فصل | جافاسكريبت: {js_cnt} فصل | ثقافة مالية: {fin_cnt} سؤال | بنك الإجابات: {total_ans}]"
        )

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """إنشاء الجداول اللازمة إذا لم تكن موجودة"""
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_answers (
                question_id INTEGER PRIMARY KEY,
                chapter_id INTEGER,
                question_type TEXT,
                correct_choice_id INTEGER,
                correct_content TEXT,
                model_answer TEXT,
                explanation TEXT,
                question_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_chapters (
                chapter_id INTEGER PRIMARY KEY,
                course_id TEXT,
                seq INTEGER,
                name TEXT,
                url TEXT,
                test_type TEXT,
                question_count INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                diamond INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                password TEXT,
                grade TEXT DEFAULT 'grade_1',
                subject TEXT DEFAULT 'programming',
                active_course_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS financial_literacy_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question_text TEXT,
                options_json TEXT,
                correct_answer TEXT,
                explanation TEXT,
                topic TEXT,
                source TEXT DEFAULT 'user_training',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS subscription_groups (
                group_id TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                tier_name TEXT NOT NULL,
                max_users INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, user_id)
            );
            """)

            
            conn.execute("""
            CREATE TABLE IF NOT EXISTS completed_group_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                grade TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS group_started_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                user_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS free_user_trial (
                user_id INTEGER PRIMARY KEY,
                solved_count INTEGER DEFAULT 0,
                last_chapter_seq INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # تهيئة كلمات مرور الأدمن الافتراضية
            row = conn.execute("SELECT value FROM admin_config WHERE key = 'passwords'").fetchone()
            if not row:
                conn.execute("INSERT INTO admin_config (key, value) VALUES ('passwords', ?)", (json.dumps(["123", "17890"]),))

            conn.commit()

    def seed_default_chapters(self):
        """تخزين وتأكيد وجود جميع روابط الفصول في بنك الروابط محلياً"""
        # مسار بايثون
        self.save_chapters_batch(DEFAULT_PYTHON_CHAPTERS, course_id="python_short_ar", sync_to_cloud=False)
        # مسار جافاسكريبت
        self.save_chapters_batch(DEFAULT_JS_CHAPTERS, course_id="javascript_ar", sync_to_cloud=False)

    def save_chapter(
        self,
        chapter_id: int,
        course_id: str = "python_short_ar",
        seq: int = 1,
        name: str = "",
        test_type: str = "review",
        question_count: int = 0,
        completed: int = 0,
        diamond: int = 0,
        sync_to_cloud: bool = True
    ) -> bool:
        """حفظ أو تحديث بيانات ورابط الفصل في قاعدة البيانات"""
        clean_url = f"https://me-tp.qureo.education/chapter/{chapter_id}"
        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT INTO saved_chapters (
                    chapter_id, course_id, seq, name, url, test_type,
                    question_count, completed, diamond, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE saved_chapters.name END,
                    url = excluded.url,
                    test_type = excluded.test_type,
                    question_count = CASE WHEN excluded.question_count > 0 THEN excluded.question_count ELSE saved_chapters.question_count END,
                    completed = excluded.completed,
                    diamond = excluded.diamond,
                    updated_at = CURRENT_TIMESTAMP;
                """, (chapter_id, course_id, seq, name, clean_url, test_type, question_count, completed, diamond))
                conn.commit()
            if sync_to_cloud and self.firebase and self.firebase.is_connected:
                self.firebase.save_chapter(
                    chapter_id=chapter_id,
                    course_id=course_id,
                    seq=seq,
                    name=name,
                    url=clean_url,
                    test_type=test_type,
                    question_count=question_count,
                    completed=completed,
                    diamond=diamond
                )
            return True
        except Exception as e:
            logger.error(f"Error saving chapter {chapter_id}: {e}")
            return False

    def save_chapters_batch(self, chapters: list, course_id: str = "python_short_ar", sync_to_cloud: bool = True):
        """حفظ قائمة فصول المسار دفعة واحدة"""
        for c in chapters:
            self.save_chapter(
                chapter_id=c.get("id"),
                course_id=course_id,
                seq=c.get("seq", 1),
                name=c.get("name", ""),
                test_type=c.get("test_type", "review"),
                question_count=c.get("question_count", 0),
                completed=1 if c.get("completed") else 0,
                diamond=c.get("diamond", 0),
                sync_to_cloud=sync_to_cloud
            )

    def update_chapter_progress(self, chapter_id: int, completed: int = 1, diamond: int = 5):
        """تحديث حالة إنجاز الفصل والماسات"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                UPDATE saved_chapters
                SET completed = ?, diamond = ?, updated_at = CURRENT_TIMESTAMP
                WHERE chapter_id = ?
                """, (completed, diamond, chapter_id))
                conn.commit()
            if self.firebase and self.firebase.is_connected:
                self.firebase.update_chapter_progress(chapter_id, completed=completed, diamond=diamond)
            logger.info(f"✅ [تقدم الفصل] تم تحديث إنجاز الفصل ({chapter_id}) بنجاح (مكتمل: {completed} | الماسات: {diamond}/5 💎)")
        except Exception as e:
            logger.error(f"Error updating chapter progress {chapter_id}: {e}")

    def get_all_chapters(self, course_id: str = "python_short_ar") -> List[Dict[str, Any]]:
        """جلب جميع الفصول المسجلة للمسار مرتبة حسب التسلسل"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM saved_chapters WHERE course_id = ? ORDER BY seq ASC",
                    (course_id,)
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []

    def get_chapter(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """جلب بيانات فصل محدد ورابطه النظيف"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM saved_chapters WHERE chapter_id = ?", (chapter_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def get_first_uncompleted_chapter(self, course_id: str = "python_short_ar") -> Optional[Dict[str, Any]]:
        """جلب أول فصل غير مكتمل للمتابعة منه فوراً دون البدء من البداية"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM saved_chapters WHERE course_id = ? AND completed = 0 ORDER BY seq ASC LIMIT 1",
                    (course_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception:
            return None

    def get_uncompleted_chapters(self, course_id: str = "python_short_ar") -> List[Dict[str, Any]]:
        """جلب جميع الفصول المتبقية التي لم تكتمل بعد للمتابعة منها مرتبة حسب التسلسل"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM saved_chapters WHERE course_id = ? AND completed = 0 ORDER BY seq ASC",
                    (course_id,)
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []

    def save_choice_answer(
        self,
        question_id: int,
        chapter_id: int,
        correct_choice_id: int,
        correct_content: str = "",
        explanation: str = "",
        question_text: str = ""
    ) -> bool:
        """حفظ أو تحديث إجابة سؤال اختيار من متعدد"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT INTO saved_answers (
                    question_id, chapter_id, question_type, correct_choice_id,
                    correct_content, explanation, question_text, updated_at
                ) VALUES (?, ?, 'choice', ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id) DO UPDATE SET
                    correct_choice_id = excluded.correct_choice_id,
                    correct_content = excluded.correct_content,
                    explanation = excluded.explanation,
                    updated_at = CURRENT_TIMESTAMP;
                """, (question_id, chapter_id, correct_choice_id, correct_content, explanation, question_text))
                conn.commit()
            if self.firebase and self.firebase.is_connected:
                self.firebase.save_answer(
                    question_id=question_id,
                    chapter_id=chapter_id,
                    question_type="choice",
                    correct_choice_id=correct_choice_id,
                    correct_content=correct_content,
                    explanation=explanation,
                    question_text=question_text
                )
            logger.info(f"✅ [بنك الإجابات] تم حفظ إجابة السؤال الاختياري ({question_id}) بنجاح.")
            return True
        except Exception as e:
            logger.error(f"Error saving choice answer {question_id}: {e}")
            return False

    def save_description_answer(
        self,
        question_id: int,
        chapter_id: int,
        model_answer: str,
        explanation: str = "",
        question_text: str = ""
    ) -> bool:
        """حفظ أو تحديث إجابة سؤال مقالي / كود برمجى"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT INTO saved_answers (
                    question_id, chapter_id, question_type, model_answer,
                    explanation, question_text, updated_at
                ) VALUES (?, ?, 'description', ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id) DO UPDATE SET
                    model_answer = excluded.model_answer,
                    explanation = excluded.explanation,
                    updated_at = CURRENT_TIMESTAMP;
                """, (question_id, chapter_id, model_answer, explanation, question_text))
                conn.commit()
            if self.firebase and self.firebase.is_connected:
                self.firebase.save_answer(
                    question_id=question_id,
                    chapter_id=chapter_id,
                    question_type="description",
                    model_answer=model_answer,
                    explanation=explanation,
                    question_text=question_text
                )
            logger.info(f"✅ [بنك الإجابات] تم حفظ الإجابة النموذجية البرمجية للسؤال ({question_id}) بنجاح.")
            return True
        except Exception as e:
            logger.error(f"Error saving description answer {question_id}: {e}")
            return False

    def get_answer(self, question_id: int) -> Optional[Dict[str, Any]]:
        """جلب الإجابة المحفوظة لسؤال محدد"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM saved_answers WHERE question_id = ?",
                    (question_id,)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

            # إذا لم يتم العثور عليها محلياً وفيربيس متصل، جلبها وحفظها محلياً
            if self.firebase and self.firebase.is_connected:
                cloud_ans = self.firebase.get_answer(question_id)
                if cloud_ans:
                    q_type = cloud_ans.get("question_type", "choice")
                    if q_type == "choice":
                        self.save_choice_answer(
                            question_id=cloud_ans.get("question_id", question_id),
                            chapter_id=cloud_ans.get("chapter_id", 0),
                            correct_choice_id=cloud_ans.get("correct_choice_id"),
                            correct_content=cloud_ans.get("correct_content", ""),
                            explanation=cloud_ans.get("explanation", ""),
                            question_text=cloud_ans.get("question_text", "")
                        )
                    else:
                        self.save_description_answer(
                            question_id=cloud_ans.get("question_id", question_id),
                            chapter_id=cloud_ans.get("chapter_id", 0),
                            model_answer=cloud_ans.get("model_answer", ""),
                            explanation=cloud_ans.get("explanation", ""),
                            question_text=cloud_ans.get("question_text", "")
                        )
                    return cloud_ans
        except Exception as e:
            logger.error(f"Error retrieving answer for {question_id}: {e}")
        return None

    def get_total_count(self) -> int:
        """إجمالي عدد الأسئلة والإجابات المخزنة في التطبيق"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM saved_answers")
                row = cursor.fetchone()
                return row["cnt"] if row else 0
        except Exception:
            return 0

    def get_chapter_answers(self, chapter_id: int) -> List[Dict[str, Any]]:
        """جلب جميع الإجابات المحفوظة لفصل معين"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM saved_answers WHERE chapter_id = ? ORDER BY question_id ASC",
                    (chapter_id,)
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []

    def save_user_profile(
        self,
        user_id: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        grade: Optional[str] = None,
        subject: Optional[str] = None,
        active_course_url: Optional[str] = None
    ) -> bool:
        """حفظ أو تحديث تفضيلات المستخدم (الصف والمادة فقط - دون تخزين بيانات تسجيل الدخول أبداً لحماية الخصوصية)"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                INSERT INTO bot_users (user_id, username, password, grade, subject, active_course_url, updated_at)
                VALUES (?, NULL, NULL, COALESCE(?, 'grade_1'), COALESCE(?, 'programming'), ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = NULL,
                    password = NULL,
                    grade = CASE WHEN excluded.grade IS NOT NULL THEN excluded.grade ELSE bot_users.grade END,
                    subject = CASE WHEN excluded.subject IS NOT NULL THEN excluded.subject ELSE bot_users.subject END,
                    active_course_url = CASE WHEN excluded.active_course_url IS NOT NULL THEN excluded.active_course_url ELSE bot_users.active_course_url END,
                    updated_at = CURRENT_TIMESTAMP;
                """, (user_id, grade, subject, active_course_url))
                conn.commit()
            if self.firebase and self.firebase.is_connected:
                self.firebase.save_user_profile(
                    user_id=user_id,
                    username=None,
                    password=None,
                    grade=grade,
                    subject=subject,
                    active_course_url=active_course_url
                )
            return True
        except Exception as e:
            logger.error(f"Error saving user profile {user_id}: {e}")
            return False

    def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """جلب تفضيلات المستخدم (مع ضمان عدم إرجاع أي اسم مستخدم أو كلمة مرور للحفاظ على الخصوصية التامة)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT user_id, grade, subject, active_course_url, updated_at FROM bot_users WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    res = dict(row)
                    res["username"] = None
                    res["password"] = None
                    return res
        except Exception as e:
            logger.error(f"Error retrieving user profile {user_id}: {e}")
        return None

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """اسم بديل للتوافق البرمجي لجلب بيانات المستخدم"""
        return self.get_user_profile(user_id)

    def clear_user_credentials(self, user_id: int) -> bool:
        """مسح بيانات تسجيل الدخول للمستخدم (عند تبديل الحساب أو تسجيل الخروج)"""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE bot_users SET username = NULL, password = NULL, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
            if self.firebase and self.firebase.is_connected:
                self.firebase.clear_user_credentials(user_id)
            return True
        except Exception as e:
            logger.error(f"Error clearing credentials for {user_id}: {e}")
            return False

    def save_financial_question(
        self,
        question_text: str,
        options: List[str],
        correct_answer: str,
        explanation: str = "",
        topic: str = "",
        user_id: Optional[int] = None,
        source: str = "training_image",
        sync_to_cloud: bool = True
    ) -> int:
        """حفظ سؤال ثقافة مالية تم تدريب البوت عليه في بنك الأسئلة الدائم"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                INSERT INTO financial_literacy_bank (
                    user_id, question_text, options_json, correct_answer, explanation, topic, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, question_text, json.dumps(options, ensure_ascii=False), correct_answer, explanation, topic, source))
                conn.commit()
                last_id = cursor.lastrowid
            if sync_to_cloud and self.firebase and self.firebase.is_connected:
                self.firebase.save_financial_question(
                    question_text=question_text,
                    options=options,
                    correct_answer=correct_answer,
                    explanation=explanation,
                    topic=topic,
                    user_id=user_id,
                    source=source
                )
            return last_id
        except Exception as e:
            logger.error(f"Error saving financial question: {e}")
            return 0

    def find_financial_answer(self, question_text: str) -> Optional[Dict[str, Any]]:
        """البحث عن إجابة سؤال ثقافة مالية في البنك عبر المطابقة الدقيقة والتطبيع اللغوي العربي والكلمات المفتاحية"""
        if not question_text:
            return None
        try:
            clean_q = question_text.strip().replace("&#34;", '"').replace("&quot;", '"').replace("'", "")
            norm_q = normalize_arabic_text(clean_q)

            with self._get_connection() as conn:
                # 1. مطابقة مباشرة بنص السؤال الأصلي
                cursor = conn.execute(
                    "SELECT * FROM financial_literacy_bank WHERE question_text = ? LIMIT 1",
                    (clean_q,)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

                # 2. مطابقة بالـ LIKE على بداية السؤال
                short_q = clean_q[:35]
                cursor = conn.execute(
                    "SELECT * FROM financial_literacy_bank WHERE question_text LIKE ? LIMIT 1",
                    (f"%{short_q}%",)
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

                # 3. مطابقة شاملة باستخدام التطبيع اللغوي العربي على جميع السجلات
                cursor = conn.execute("SELECT * FROM financial_literacy_bank")
                rows = cursor.fetchall()
                for r in rows:
                    db_norm = normalize_arabic_text(r["question_text"])
                    if norm_q and (norm_q == db_norm or norm_q in db_norm or db_norm in norm_q):
                        return dict(r)

                # 4. مطابقة بالكلمات المفتاحية الأساسية
                stopwords = {"التي", "الذي", "التي", "اي", "مما", "يلي", "هو", "هي", "ما", "في", "من", "عن", "علي", "على", "الي", "إلى", "بين", "مع"}
                words = [w for w in norm_q.split() if len(w) >= 2 and w not in stopwords]
                if len(words) >= 2:
                    best_match = None
                    max_matches = 0
                    for r in rows:
                        db_norm = normalize_arabic_text(r["question_text"])
                        matched_cnt = sum(1 for w in words if w in db_norm)
                        if matched_cnt > max_matches and (matched_cnt >= 2 or matched_cnt >= len(words) * 0.5):
                            max_matches = matched_cnt
                            best_match = r
                    if best_match and max_matches >= 2:
                        return dict(best_match)

        except Exception as e:
            logger.error(f"Error finding financial answer: {e}")
        return None

    def save_financial_training_question(
        self,
        user_id: int,
        question_text: str,
        options: Any,
        correct_answer: str,
        explanation: str = "",
        topic: str = "الثقافة المالية"
    ) -> int:
        """حفظ أو تحديث سؤال في بنك الثقافة المالية"""
        opts_list = []
        if isinstance(options, list):
            for opt in options:
                if isinstance(opt, dict):
                    opts_list.append(opt.get("text", str(opt)))
                else:
                    opts_list.append(str(opt))
        elif isinstance(options, dict):
            opts_list = list(options.values())

        return self.save_financial_question(
            question_text=question_text,
            options=opts_list,
            correct_answer=correct_answer,
            explanation=explanation,
            topic=topic,
            user_id=user_id,
            source="spx_auto_solver"
        )

    def seed_spx_default_questions(self):
        """تغذية البنك بقاعدة المعرفة الشاملة لجميع وحدات منهج الثقافة المالية الـ 6 المعتمدة رسمياً"""
        default_q = [
            # ==========================================
            # الوحدة 1: أساسيات المال والتمويل (Units 19)
            # ==========================================
            {
                "question": "في الحياة اليومية، أي موقف يوضّح بأفضل شكل استخدام وظيفة 'وحدة الحساب' للمال؟",
                "options": [
                    "عدّ الأوراق النقدية في محفظتك لمعرفة كم لديك من المال",
                    "عند الشراء، النظر إلى السعر واختيار الأفضل بمقارنة 'الغالي' و'الرخيص'",
                    "استلام المصروف والتفكير فيما إذا كنت ستدّخره أو تصرفه الآن",
                    "مبادلة أشياء مع صديق بتسليم كل منكما ما يملكه للآخر"
                ],
                "answer": "عند الشراء، النظر إلى السعر واختيار الأفضل بمقارنة 'الغالي' و'الرخيص'",
                "explanation": "وحدة الحساب هي وظيفة مقارنة قيمة السلع والخدمات المختلفة وفق معيار نقدي موحد.",
                "topic": "الوظائف الثلاث للمال"
            },
            {
                "question": "لنفترض أنك تحتفظ بألف جنيه مخزّنة في مكان ما وتستخدمها بعد سنوات. إذا تقدّم التضخم خلال تلك المدة، أي مما يلي يصف بدقة ما يحدث لتلك الألف جنيه؟",
                "options": [
                    "تبقى القيمة الاسمية للألف جنيه كما هي، لكن الكمية التي يمكنك شراؤها بها أقل من السابق",
                    "تتغيّر القيمة الاسمية للألف جنيه أيضًا، وتظل قادرًا على شراء نفس الكمية كما كانت من قبل",
                    "ترتفع القيمة الاسمية للألف جنيه مع التضخم عبر السنوات، وتزداد أيضًا الكمية التي يمكنك شراؤها",
                    "تتقادم ورقة الألف جنيه فتنخفض المبالغ التي تقبلها المتاجر بدلًا منها"
                ],
                "answer": "تبقى القيمة الاسمية للألف جنيه كما هي، لكن الكمية التي يمكنك شراؤها بها أقل من السابق",
                "explanation": "التضخم يقلل من القوة الشرائية الحقيقية للنقود بينما يظل الرقم الاسمي كما هو.",
                "topic": "دور المال"
            },
            {
                "question": "لنفترض أنك تقارن الأسعار في قائمة، تختار واحدًا، تدفع بالمال، وتحتفظ بالباقي في محفظتك دون استخدامه. أي مما يلي يصف بدقة وظائف المال الموجودة في هذا المشهد بأكمله؟",
                "options": [
                    "فقط فعل الدفع يوضّح وظيفة المال، ولا توجد وظيفة في التصرفات الأخرى",
                    "فقط فعل مقارنة الأسعار يوضّح وظيفة المال، ولا توجد وظيفة في التصرفات الأخرى",
                    "مقارنة الأسعار، والدفع، والاحتفاظ بالباقي، كل تصرف يوضّح وظيفة مختلفة",
                    "فقط فعل الاحتفاظ بالمال يوضّح وظيفة المال، ولا توجد وظيفة في التصرفات الأخرى"
                ],
                "answer": "مقارنة الأسعار، والدفع، والاحتفاظ بالباقي، كل تصرف يوضّح وظيفة مختلفة",
                "explanation": "المقارنة بالسعر هي وحدة حساب، والدفع وسيلة تبادل، والاحتفاظ به مخزن للقيمة.",
                "topic": "الوظائف الثلاث للمال"
            },
            {
                "question": "لديك مبلغ من المال وتفكر في كيفية التصرف به على مدى السنوات القادمة. في مجتمع يُتوقع أن يستمر فيه التضخم، ما هو النهج الأكثر منطقية؟",
                "options": [
                    "استخدام بعضه فيما تحتاجه الآن، والاحتفاظ ببعضه بشكل آخر، والنظر في خيارات غير الادّخار فقط",
                    "الاحتفاظ بكل المال دون استخدام أي منه، وسحبه فقط عند الحاجة",
                    "صرف كل المال فورًا وعدم الاحتفاظ بأي مال على الإطلاق",
                    "الادّخار هو الأكثر أمانًا في كل الحالات، فاترك كل المال كما هو ولا تستخدمه"
                ],
                "answer": "استخدام بعضه فيما تحتاجه الآن، والاحتفاظ ببعضه بشكل آخر، والنظر في خيارات غير الادّخار فقط",
                "explanation": "في ظل التضخم، يجب تنويع الموارد والبحث عن أوعية استثمارية تحافظ على القوة الشرائية.",
                "topic": "دور المال"
            },
            {
                "question": "ما هي وظائف المال المُضمَّنة في هذا المشهد؟ 'شخص ينظر إلى أسعار الكشري (بخمسة وعشرين جنيهًا) والساندويتش (بثلاثين جنيهًا) في متجر، يختار الساندويتش، يأخذ ثلاثين جنيهًا من محفظته للدفع، ويحتفظ بالباقي في محفظته دون استخدامه حتى الأسبوع القادم.'",
                "options": [
                    "فقط وظيفة 'وحدة الحساب' موجودة لأنه 'قارن بالسعر'",
                    "فقط وظيفة 'وسيلة التبادل' موجودة لأنه 'سلّم المال للشراء'",
                    "فقط وظيفة 'مخزن للقيمة' موجودة لأنه 'احتفظ به'",
                    "الوظائف الثلاث جميعًا موجودة: 'المقارنة بالسعر، والدفع بالمال، والاحتفاظ به'"
                ],
                "answer": "الوظائف الثلاث جميعًا موجودة: 'المقارنة بالسعر، والدفع بالمال، والاحتفاظ به'",
                "explanation": "المشهد يجمع الوظائف الاقتصادية الثلاث الكلاسيكية للنقود.",
                "topic": "الوظائف الثلاث للمال"
            },
            {
                "question": "ما هي الصعوبة الرئيسية التي جعلت نظام المقايضة غير عملي في المجتمعات المتطورة؟",
                "options": [
                    "صعوبة توافق رغبات الطرفين في وقت واحد وصعوبة تجزئة بعض السلع",
                    "كثرة الأموال المتداولة في الأسواق وتدني قيمتها",
                    "تدخل البنوك المركزية في فرض الأسعار بالقوة",
                    "تفضيل الناس للدفع بالبطاقات الإلكترونية بدلاً من البضائع"
                ],
                "answer": "صعوبة توافق رغبات الطرفين في وقت واحد وصعوبة تجزئة بعض السلع",
                "explanation": "المقايضة تتطلب التوافق المزدوج للرغبات (Double Coincidence of Wants) وهو نادر الحدوث باستمرار.",
                "topic": "كيف نشأ المال"
            },
            {
                "question": "لماذا تم اختيار الذهب والفضة تاريخياً ليكونا الشكل المفضل للنقود المعدنية؟",
                "options": [
                    "لأنها نادرة، متينة لا تتلف، سهلة الحمل والتجزئة، وذات قيمة ذاتية مقبولة عامة",
                    "لأنها كانت متوفرة بكثرة تفوق كميات الحبوب والماشية",
                    "لأنها سريعة التآكل والتلف مما يشجع على تدويرها بسرعة",
                    "بناءً على تعليمات البنوك الرقمية الحديثة"
                ],
                "answer": "لأنها نادرة، متينة لا تتلف، سهلة الحمل والتجزئة، وذات قيمة ذاتية مقبولة عامة",
                "explanation": "المعادن النفيسة جمعت كل شروط النقد المثالي من المتانة وقابلية التجزئة وثبات القيمة.",
                "topic": "كيف نشأ المال"
            },
            {
                "question": "ما المقصود بالنقود الورقية القانونية الإلزامية (Fiat Money) المتداولة حالياً؟",
                "options": [
                    "نقود تستمد قيمتها من ثقة المجتمع وقوة القانون الصادر عن الدولة دون إلزام بتحويلها لذهب",
                    "نقود يجب أن تكون مدعومة بنسبة 100% بسبائك ذهبية مودعة في البنك",
                    "أوراق تجارية يكتبها الأفراد لتبادل السلع دون اعتماد رسمي",
                    "نقود تُستخدم فقط في المتاجر الإلكترونية ولا تقبل في المتاجر التقليدية"
                ],
                "answer": "نقود تستمد قيمتها من ثقة المجتمع وقوة القانون الصادر عن الدولة دون إلزام بتحويلها لذهب",
                "explanation": "النقود القانونية الإلزامية تستند إلى ثقة المجتمع وسلطة الدولة في فرضها كوسيلة سداد إبراء للذمة.",
                "topic": "أشكال المال الحديث"
            },
            {
                "question": "ما هو الدور الرئيسي لعملية الوساطة المالية التي تقوم بها البنوك في الاقتصاد؟",
                "options": [
                    "تحويل الفائض المالي من المدخرين وتوجيهه كقروض وتمويل للمستثمرين وأصحاب المشاريع",
                    "طباعة الأوراق النقدية وتوزيعها مجاناً على المواطنين",
                    "تحديد أسعار الخضراوات والفاكهة في الأسواق المحلية",
                    "منع المواطنين من إنفاق أموالهم لحمايتهم من التضخم"
                ],
                "answer": "تحويل الفائض المالي من المدخرين وتوجيهه كقروض وتمويل للمستثمرين وأصحاب المشاريع",
                "explanation": "الوساطة المالية تربط بين وحدات الفائض المالي ووحدات العجز المالي لتعظيم الاستثمار والإنتاج.",
                "topic": "الوساطة المالية"
            },
            {
                "question": "أي من المؤسسات التالية تعتبر المسؤولة الأولى عن إدارة السياسة النقدية وإصدار العملة والرقابة على الجهاز المصرفي؟",
                "options": [
                    "البنك المركزي",
                    "البنوك التجارية الاستثمارية",
                    "شركات التأمين الخاصة",
                    "بورصة الأوراق المالية"
                ],
                "answer": "البنك المركزي",
                "explanation": "البنك المركزي هو بنك البنوك ومستشار الحكومة المالي وهو السلطة النقدية العليا.",
                "topic": "أنواع المؤسسات المالية وأدوارها"
            },
            {
                "question": "وفقاً لآليات السوق وقانون العرض والطلب، ماذا يحدث لسعر سلعة ما إذا زاد الطلب عليها بشكل ملحوظ مع ثبات الكمية المعروضة؟",
                "options": [
                    "يرتفع سعر السلعة في السوق",
                    "ينخفض سعر السلعة فوراً",
                    "يبقى السعر ثابتاً دون أي تغيير",
                    "تختفي السلعة تماماً من التداول القانوني"
                ],
                "answer": "يرتفع سعر السلعة في السوق",
                "explanation": "زيادة الطلب مع ثبات العرض تؤدي إلى تنافس المشترين مما يرفع السعر التوازني.",
                "topic": "آليات السوق وتحديد الأسعار"
            },
            {
                "question": "ما هو المؤشر الاقتصادي الذي يقيس القيمة السوقية الإجمالية لكافة السلع والخدمات النهائية المنتجة داخل دولة ما خلال عام؟",
                "options": [
                    "الناتج المحلي الإجمالي (GDP)",
                    "مؤشر أسعار المستهلك (CPI)",
                    "معدل البطالة العام",
                    "الرصيد الاحتياطي للبنوك"
                ],
                "answer": "الناتج المحلي الإجمالي (GDP)",
                "explanation": "الناتج المحلي الإجمالي هو المقياس الأشمل والأهم لقياس حجم النشاط والنمو الاقتصادي للدولة.",
                "topic": "المؤشرات الاقتصادية"
            },
            {
                "question": "ما هو المقدار الشرعي لزكاة المال المفروضة على الأموال النقدية التي بلغت النصاب وحال عليها الحول؟",
                "options": [
                    "2.5% من إجمالي المبلغ (ربع العشر)",
                    "5% من إجمالي المبلغ (نصف العشر)",
                    "10% من إجمالي المبلغ (العشر كاملاً)",
                    "20% من إجمالي المبلغ (الخُمس)"
                ],
                "answer": "2.5% من إجمالي المبلغ (ربع العشر)",
                "explanation": "زكاة المال محددة شرعاً بربع العشر أي 2.5% من المال الفائض البالغ للنصاب بعد مرور عام هجري كامل.",
                "topic": "فهم الزكاة"
            },

            # ==========================================
            # الوحدة 2: أساسيات الأعمال والاقتصاد (Unit 20)
            # ==========================================
            {
                "question": "ما هي الميزة الجوهرية لشركات المساهمة التي تميزها عن المنشآت الفردية؟",
                "options": [
                    "مسؤولية المساهمين محدودة بقيمة أسهمهم فقط وسهولة تداول الملكية وجمع رؤوس أموال ضخمة",
                    "أن صاحب الشركة مسؤول عن كافة ديونها من أمواله الخاصة الشخصية",
                    "صعوبة نقل الملكية من شخص لآخر إلا بموافقة جميع الشركاء",
                    "إعفاء الشركة التام من أي التزامات ضريبية أو قانونية"
                ],
                "answer": "مسؤولية المساهمين محدودة بقيمة أسهمهم فقط وسهولة تداول الملكية وجمع رؤوس أموال ضخمة",
                "explanation": "المسؤولية المحدودة تحمي الثروة الشخصية للمساهم وتسمح بتوسيع قاعدة المستثمرين.",
                "topic": "أنواع ملكية المشاريع التجارية"
            },
            {
                "question": "ما هو المفهوم الذي يعبر عن التزام الشركة الأخلاقي والطوعي بالمساهمة في التنمية المستدامة ورعاية المجتمع والبيئة؟",
                "options": [
                    "المسؤولية الاجتماعية للشركات (CSR)",
                    "تعظيم الربح المحاسبي السريع",
                    "التوسع التجاري الاحتكاري",
                    "تخفيض تكاليف أجور العاملين"
                ],
                "answer": "المسؤولية الاجتماعية للشركات (CSR)",
                "explanation": "المسؤولية الاجتماعية تعني اهتمام الشركة بالأبعاد البيئية والمجتمعية جنباً إلى جنب مع أهدافها الربحية.",
                "topic": "المسؤولية الاجتماعية للشركات (CSR)"
            },
            {
                "question": "ماذا تمثل 'سلسلة التوريد' (Supply Chain) في عالم الأعمال؟",
                "options": [
                    "الشبكة المتكاملة من الأنشطة والمؤسسات التي تنقل المنتج من مرحلة المادة الخام حتى وصوله للمستهلك النهائي",
                    "قائمة الأسعار المعلنة في المتاجر الكبرى فقط",
                    "طريقة نقل الأموال بين البنوك المركزية عبر الحسابات",
                    "عقود التوظيف المبرمة بين أصحاب العمل والموظفين"
                ],
                "answer": "الشبكة المتكاملة من الأنشطة والمؤسسات التي تنقل المنتج من مرحلة المادة الخام حتى وصوله للمستهلك النهائي",
                "explanation": "سلسلة التوريد تشمل الموردين، المصانع، المستودعات، شركات النقل، ومنافذ التوزيع.",
                "topic": "سلاسل التوريد وسلاسل القيمة"
            },
            {
                "question": "ما الفرق بين النفقات الثابتة والنفقات المتغيرة في مشروع تجاري؟",
                "options": [
                    "النفقات الثابتة لا تتغير بتغير حجم الإنتاج كالإيجار، بينما المتغيرة ترتبط مباشرة بكمية الإنتاج كالمواد الخام",
                    "النفقات الثابتة تدفع مرة واحدة في العمر فقط، والمتغيرة تدفع يومياً",
                    "النفقات المتغيرة لا يمكن حسابها في الدفاتر المحاسبية",
                    "النفقات الثابتة خاصة بالضرائب الحكومية فقط"
                ],
                "answer": "النفقات الثابتة لا تتغير بتغير حجم الإنتاج كالإيجار، بينما المتغيرة ترتبط مباشرة بكمية الإنتاج كالمواد الخام",
                "explanation": "التكاليف الثابتة تدفع حتى لو توقف الإنتاج كالإيجار والتأمين، بينما التكاليف المتغيرة تزيد بزيادة الإنتاج.",
                "topic": "فهم النفقات"
            },

            # ==========================================
            # الوحدة 3: التمويل الشخصي والائتمان (Unit 21)
            # ==========================================
            {
                "question": "ما هي النسبة الموصى بها في قاعدة الميزانية الشهيرة (50/30/20) لتوزيع الدخل؟",
                "options": [
                    "50% للاحتياجات الأساسية، 30% للرغبات والترفيه، و20% للادخار وتسديد الديون",
                    "50% للادخار، 30% للاحتياجات، و20% للرغبات",
                    "50% للترفيه، 30% للاستثمار، و20% للفواتير",
                    "50% لسداد الديون، 30% للادخار، و20% للطعام"
                ],
                "answer": "50% للاحتياجات الأساسية، 30% للرغبات والترفيه، و20% للادخار وتسديد الديون",
                "explanation": "قاعدة 50/30/20 هي المعيار الذهبي للتخطيط المالي وتوزيع الدخل بتوازن واستدامة.",
                "topic": "ما هي الميزانية؟"
            },
            {
                "question": "كيف تفرق بدقة بين 'الاحتياجات' و'الرغبات' عند وضع خطتك المالية؟",
                "options": [
                    "الاحتياجات ضرورية للبقاء والصحة (كالمأكل والمسكن)، والرغبات أشياء للراحة يمكن الاستغناء عنها",
                    "الاحتياجات هي الأشياء غالية الثمن فقط، والرغبات رخيصة الثمن دائماً",
                    "لا يوجد أي فرق بينهما فكلاهما يجب شراؤه فوراً عند توفر المال",
                    "الرغبات هي ما يفرضه القانون، والاحتياجات هي اختيارات شخصية"
                ],
                "answer": "الاحتياجات ضرورية للبقاء والصحة (كالمأكل والمسكن)، والرغبات أشياء للراحة يمكن الاستغناء عنها",
                "explanation": "التمييز بين الضروريات والكماليات هو أول خطوة لضبط الميزانية ومنع الاستدانة غير المبررة.",
                "topic": "الاحتياجات مقابل الرغبات"
            },
            {
                "question": "لماذا تُعد 'الفائدة المركبة' (Compound Interest) وسيلة فعالة جداً لتنمية المدخرات على المدى الطويل؟",
                "options": [
                    "لأنها تحسب العائد على رأس المال الأصلي بالإضافة إلى الفوائد والأرباح المتراكمة في الفترات السابقة",
                    "لأنها تعفي المستثمر من دفع أي ضرائب أو رسوم بنكية",
                    "لأنها تضمن مضاعفة رأس المال يومياً بشكل مؤكد",
                    "لأن البنك المركزي يمنحها للمقترضين مجاناً"
                ],
                "answer": "لأنها تحسب العائد على رأس المال الأصلي بالإضافة إلى الفوائد والأرباح المتراكمة في الفترات السابقة",
                "explanation": "تأثير كرة الثلج في الفائدة المركبة يجعل النمو أسيّاً بمرور السنوات الطويلة.",
                "topic": "سحر الفائدة المركبة"
            },
            {
                "question": "ما هو الإجراء المالي الأكثر حكمة لتجنب فوائد وغرامات بطاقات الائتمان (Credit Cards)؟",
                "options": [
                    "سداد كامل المبلغ المستحق قبل انتهاء فترة السماح المجانية",
                    "سداد الحد الأدنى المطلوب فقط شهرياً وتأجيل الباقي",
                    "استخدام البطاقة في السحب النقدي المباشر من ماكينات الصراف الآلي",
                    "طلب زيادة الحد الائتماني للبطاقة كل شهر"
                ],
                "answer": "سداد كامل المبلغ المستحق قبل انتهاء فترة السماح المجانية",
                "explanation": "فترة السماح تتيح استخدام أموال البنك مجاناً، بينما الاكتفاء بالحد الأدنى يراكم فوائد مركبة باهظة.",
                "topic": "كيف يعمل الائتمان"
            },

            # ==========================================
            # الوحدة 4: ريادة الأعمال (Unit 22)
            # ==========================================
            {
                "question": "ما هي السمة الأساسية التي تميز 'العقلية الريادية' في عالم الأعمال؟",
                "options": [
                    "المبادرة، وتحمل المخاطر المحسوبة، والقدرة على ابتكار حلول جديدة للمشكلات وتطويرها",
                    "تجنب أي تغيير والاعتماد الكامل على النماذج التقليدية القديمة فقط",
                    "الانتظار حتى تقدم الحكومة تمويلاً كاملاً بدون أي مجهود شخصي",
                    "البحث عن وظيفة روتينية ثابتة دون الرغبة في التوسع أو التجربة"
                ],
                "answer": "المبادرة، وتحمل المخاطر المحسوبة، والقدرة على ابتكار حلول جديدة للمشكلات وتطويرها",
                "explanation": "رائد الأعمال يتميز بالشغف، واستكشاف الفرص، والمثابرة على تحويل الأفكار إلى واقع منتج.",
                "topic": "العقلية الريادية"
            },
            {
                "question": "ماذا تعني 'نقطة التعادل' (Break-even Point) في التخطيط المالي للمشاريع الناشئة؟",
                "options": [
                    "النقطة التي تتساوى عندها الإيرادات الكلية تماماً مع التكاليف الكلية (لا ربح ولا خسارة)",
                    "النقطة التي يحقق فيها المشروع أعلى صافي أرباح تاريخية",
                    "اللحظة التي يعلن فيها المشروع إفلاسه وتصفية أصوله",
                    "تاريخ توقيع عقد الشراكة بين المؤسسين"
                ],
                "answer": "النقطة التي تتساوى عندها الإيرادات الكلية تماماً مع التكاليف الكلية (لا ربح ولا خسارة)",
                "explanation": "نقطة التعادل تمثل عتبة الأمان التي يبدأ بعدها المشروع في تحقيق أرباح حقيقية.",
                "topic": "أنواع التكاليف وإدارتها"
            },

            # ==========================================
            # الوحدة 5: أساسيات الاستثمار (Unit 23)
            # ==========================================
            {
                "question": "ما هي العلاقة الأساسية بين 'العائد المتوقع' و'درجة المخاطرة' في الاستثمار؟",
                "options": [
                    "علاقة طردية: كلما زاد العائد المحتمل المتوقع للاستثمار، زادت المخاطرة المصاحبة له",
                    "علاقة عكسية: الاستثمارات ذات العائد المرتفع تكون دائماً خالية من المخاطر",
                    "لا توجد أي علاقة بين المخاطرة والعائد إطلاقاً",
                    "المخاطرة المرتفعة تضمن تحقيق الربح في جميع الأحوال"
                ],
                "answer": "علاقة طردية: كلما زاد العائد المحتمل المتوقع للاستثمار، زادت المخاطرة المصاحبة له",
                "explanation": "قانون الاستثمار الأول ينص على أنه لا يمكن الحصول على عوائد مرتفعة دون قبول مخاطر أعلى.",
                "topic": "المخاطرة والعائد"
            },
            {
                "question": "ما هو الهدف الجوهري من تطبيق استراتيجية 'التنويع الاستثماري' (Diversification)؟",
                "options": [
                    "تقليل المخاطر الإجمالية للمحفظة عن طريق توزيع الأموال على أصول وقطاعات متنوعة",
                    "استثمار كل رأس المال بالكامل في سهم شركة واحدة واعدة",
                    "تجنب التعامل مع البورصة والبنوك وحفظ الأموال نقداً في المنزل",
                    "ضمان ربح ثابت يومي بنسبة محددة مسبقاً"
                ],
                "answer": "تقليل المخاطر الإجمالية للمحفظة عن طريق توزيع الأموال على أصول وقطاعات متنوعة",
                "explanation": "المثل الشهير 'لا تضع كل البيض في سلة واحدة' يعبر عن التنويع لحماية المحفظة من خسارة أي أصل مفرد.",
                "topic": "مبادئ التنويع"
            },
            {
                "question": "ما هو الفرق الرئيسي بين تملك 'الأسهم' وتملك 'السندات' في الشركات؟",
                "options": [
                    "السهم يمثل حصة ملكية في الشركة وأرباحه متغيرة، بينما السند صك دين بفائدة محددة وتاريخ استرداد",
                    "السهم قرض للشركة والسند ملكية في أصولها",
                    "الأسهم لا تباع في البورصة والسندات تباع فقط في المتاجر",
                    "كلاهما يحمل نفس الحقوق والالتزامات تماماً دون أي اختلاف"
                ],
                "answer": "السهم يمثل حصة ملكية في الشركة وأرباحه متغيرة، بينما السند صك دين بفائدة محددة وتاريخ استرداد",
                "explanation": "حامل السهم شريك ومالك، بينما حامل السند مقرض ودائن وله الأولوية في استرداد أمواله.",
                "topic": "أساسيات الأسهم"
            },

            # ==========================================
            # الوحدة 6: الذكاء الاصطناعي والتمويل (Unit 24)
            # ==========================================
            {
                "question": "ما هو المصطلح المعبر عن دمج التكنولوجيا الرقمية والبرمجيات المتقدمة لتقديم وتطوير الخدمات المالية والمصرفية؟",
                "options": [
                    "التكنولوجيا المالية (FinTech)",
                    "المقايضة الإلكترونية",
                    "الوساطة اليدوية",
                    "التجارة التقليدية"
                ],
                "answer": "التكنولوجيا المالية (FinTech)",
                "explanation": "مصطلح FinTech يجمع بين Finance و Technology ويشمل المدفوعات الرقمية والمحافظ والبنوك الإلكترونية.",
                "topic": "التكنولوجيا المالية والذكاء الاصطناعي في التمويل"
            },
            {
                "question": "كيف يساهم الذكاء الاصطناعي في تحسين أمان المعاملات المالية ومنع الجرائم المصرفية؟",
                "options": [
                    "التحليل الفوري لأنماط المعاملات وكشف العمليات الاحتيالية والمشبوهة وتجميدها تلقائياً",
                    "إلغاء كلمات المرور ورموز الأمان نهائياً من كافة البنوك",
                    "نشر بيانات البطاقات الائتمانية علناً لمقارنتها بالأسعار",
                    "منع المستخدمين من الشراء عبر الإنترنت بشكل دائم"
                ],
                "answer": "التحليل الفوري لأنماط المعاملات وكشف العمليات الاحتيالية والمشبوهة وتجميدها تلقائياً",
                "explanation": "نماذج التعلم الآلي تراقب ملايين المعاملات في أجزاء من الثانية وتكتشف السلوكيات الشاذة بدقة فائقة.",
                "topic": "كيف يغيّر الذكاء الاصطناعي عالم الأعمال"
            },
            {
                "question": "ما هي الفائدة الأساسية من استخدام العقود الذكية (Smart Contracts) القائمة على تقنية البلوك تشين في المعاملات المالية؟",
                "options": [
                    "التنفيذ التلقائي للشروط والاتفاقيات بدقة وأمان دون الحاجة لوسيط بشري أو جهة مركزية",
                    "إلغاء الحاجة لوجود أموال أو قيمة مالية في المعاملة",
                    "السماح بتعديل الشروط من طرف واحد في أي وقت دون علم الطرف الآخر",
                    "زيادة الرسوم المصرفية المفروضة على التحويلات"
                ],
                "answer": "التنفيذ التلقائي للشروط والاتفاقيات بدقة وأمان دون الحاجة لوسيط بشري أو جهة مركزية",
                "explanation": "العقود الذكية تُبرمج لتنفيذ بنود الاتفاق ذاتياً بمجرد تحقق الشروط المتفق عليها بأمان تام.",
                "topic": "التكنولوجيا المالية والذكاء الاصطناعي في التمويل"
            },
            {
                "question": "ما هي المهارة الأكثر أهمية للطلاب والموظفين للنجاح في سوق العمل في عصر الذكاء الاصطناعي؟",
                "options": [
                    "التفكير النقدي، وحل المشكلات المعقدة، والقدرة على التعلم المستمر واستخدام أدوات الذكاء الاصطناعي بكفاءة",
                    "حفظ المعلومات والبيانات عن ظهر قلب دون فهمها",
                    "القيام بالمهام الروتينية المتكررة باليد وتجنب استخدام الحواسيب",
                    "تجنب استخدام التكنولوجيا والعودة للسجلات الورقية القديمة"
                ],
                "answer": "التفكير النقدي، وحل المشكلات المعقدة، والقدرة على التعلم المستمر واستخدام أدوات الذكاء الاصطناعي بكفاءة",
                "explanation": "الذكاء الاصطناعي يتولى المهام الروتينية بينما تصبح المهارات التحليلية والإبداعية البشرية هي الأكثر طلباً.",
                "topic": "كيف يغيّر الذكاء الاصطناعي الوظائف والمجتمع"
            },
            {
                "question": "ما المقصود بـ 'الثقافة الرقمية للذكاء الاصطناعي' (AI Literacy) للمستهلك المالي؟",
                "options": [
                    "فهم كيفية عمل أدوات الذكاء الاصطناعي، والتعرف على توصياتها المالية، وحماية البيانات الشخصية والخصوصية",
                    "شراء أحدث الهواتف الذكية كل عام",
                    "عدم استخدام أي خدمات بنكية رقمية مطلقاً",
                    "السماح لجميع التطبيقات بالوصول لكافة البيانات والصور والحسابات دون قيود"
                ],
                "answer": "فهم كيفية عمل أدوات الذكاء الاصطناعي، والتعرف على توصياتها المالية، وحماية البيانات الشخصية والخصوصية",
                "explanation": "الثقافة الرقمية تمكن الفرد من استخدام التكنولوجيا الذكية بوعي ومسؤولية مع تجنب المخاطر السيبرانية.",
                "topic": "ما هي الثقافة الرقمية للذكاء الاصطناعي؟"
            },
            {
                "question": "ما هو الأثر الاقتصادي الأساسي لدفع الزكاة في المجتمع الإسلامي؟",
                "options": [
                    "تحريك عجلة الاقتصاد وزيادة القوة الشرائية للفقراء وتدوير الأموال الراكدة بدلاً من كنزها",
                    "تقليل النشاط التجاري وتثبيط المستثمرين عن العمل",
                    "رفع أسعار السلع الغذائية في الأسواق بصورة مفاجئة",
                    "تشجيع الناس على عدم العمل والاعتماد على المساعدات دائماً"
                ],
                "answer": "تحريك عجلة الاقتصاد وزيادة القوة الشرائية للفقراء وتدوير الأموال الراكدة بدلاً من كنزها",
                "explanation": "الزكاة تمنع كنز الأموال وتعيد ضخ السيولة في دورة الاستهلاك والإنتاج مما ينشط الاقتصاد القومي.",
                "topic": "كيف تُحسب الزكاة"
            },
            {
                "question": "أي من الفئات التالية تعتبر من مصارف الزكاة الشرعية الثمانية المذكورة في القرآن الكريم؟",
                "options": [
                    "الفقراء والمساكين والغارمون وفي سبيل الله وابن السبيل",
                    "بناء الأبراج التجارية الفاخرة للشركات الخاصة",
                    "تسديد فواتير الترفيه للأثرياء ورجال الأعمال",
                    "شراء الأسهم الاستثمارية في البورصة للمضاربة اليومية"
                ],
                "answer": "الفقراء والمساكين والغارمون وفي سبيل الله وابن السبيل",
                "explanation": "مصارف الزكاة حددتها الآية الكريمة (إنما الصدقات للفقراء والمساكين والعاملين عليها...) وهي ثمانية أصناف حصراً.",
                "topic": "من يستحق الزكاة؟"
            },
            {
                "question": "ما هو الفرق الجوهري بين النظام الاقتصادي الرأسمالي والنظام الاقتصادي الاشتراكي؟",
                "options": [
                    "الرأسمالية تعتمد على الملكية الفردية وحرية السوق، بينما الاشتراكية تعتمد على ملكية الدولة العامة لوسائل الإنتاج والتخطيط المركزي",
                    "الرأسمالية تمنع التجارة والاشتراكية تشجعها بالكامل",
                    "الاشتراكية تستخدم النقود والرأسمالية تعتمد على المقايضة فقط",
                    "لا يوجد أي فرق اقتصادي بين النظامين"
                ],
                "answer": "الرأسمالية تعتمد على الملكية الفردية وحرية السوق، بينما الاشتراكية تعتمد على ملكية الدولة العامة لوسائل الإنتاج والتخطيط المركزي",
                "explanation": "الفارق الجوهري يكمن في ملكية وسائل الإنتاج (أفراد مقابل دولة) وآلية تحديد الأسعار (سوق حر مقابل تسعير جبري).",
                "topic": "النظم الاقتصادية"
            },
            {
                "question": "كيف يؤثر التضخم المرتفع على أصحاب الدخول الثابتة في المجتمع؟",
                "options": [
                    "يؤدي إلى انخفاض قوتهم الشرائية الحقيقية لأن الأسعار ترتفع بينما تظل رواتبهم الاسمية ثابتة",
                    "يزيد من قدرتهم على شراء السلع والخدمات الفاخرة بسهولة",
                    "يخفض تكاليف المعيشة ويزيد من مدخراتهم البنكية",
                    "لا يتأثر أصحاب الدخول الثابتة بأي شكل من أشكال التضخم"
                ],
                "answer": "يؤدي إلى انخفاض قوتهم الشرائية الحقيقية لأن الأسعار ترتفع بينما تظل رواتبهم الاسمية ثابتة",
                "explanation": "التضخم يلتهم القوة الشرائية للنقود، وأصحاب الرواتب الثابتة هم الأكثر تضرراً ما لم تعدل أجورهم بنسبة التضخم.",
                "topic": "المؤشرات الاقتصادية"
            },
            {
                "question": "ما هو صندوق الطوارئ المالي (Emergency Fund) وما هو حجمه الموصى به مالياً؟",
                "options": [
                    "مبلغ مالي مخصص لمواجهة الأزمات غير المتوقعة ويعادل نفقات معيشة 3 إلى 6 أشهر",
                    "قرض بنكي يسحبه الفرد للسفر والسياحة والترفيه",
                    "حساب استثماري عالي المخاطر للمضاربة اليومية في البورصة",
                    "مبلغ يتم إنفاقه فوراً في نهاية كل شهر على المشتريات الترفيهية"
                ],
                "answer": "مبلغ مالي مخصص لمواجهة الأزمات غير المتوقعة ويعادل نفقات معيشة 3 إلى 6 أشهر",
                "explanation": "صندوق الطوارئ هو صمام الأمان المالي الأول لحماية الأسرة من الوقوع في الديون عند حدوث ظرف طارئ كفقدان العمل أو المرض.",
                "topic": "التحضير لمخاطر المستقبل"
            },
            {
                "question": "ما هو مفهوم الجدارة الائتمانية والتقرير الائتماني (I-Score)؟",
                "options": [
                    "سجل يوثق التزام العميل بسداد أقساطه وديونه وفواتيره السابقة في مواعيدها المحددة وتعتمد عليه البنوك لمنح التمويل",
                    "رصيد النقود الورقية الموجودة في محفظة الفرد الشخصية",
                    "عدد أصدقاء العميل على منصات التواصل الاجتماعي",
                    "شهادة تقدير مدرسية تمنح للطلاب المتفوقين في مادة المحاسبة"
                ],
                "answer": "سجل يوثق التزام العميل بسداد أقساطه وديونه وفواتيره السابقة في مواعيدها المحددة وتعتمد عليه البنوك لمنح التمويل",
                "explanation": "التقرير الائتماني يعكس مدى انضباط العميل المالي وموثوقيته في الوفاء بالالتزامات التعاقدية للجهات المانحة للائتمان.",
                "topic": "المسؤولية عن الديون وحقوق المستهلك"
            },
            {
                "question": "ما المقصود بـ 'القيمة المقترحة' (Value Proposition) في نموذج العمل التجاري للمشاريع الناشئة؟",
                "options": [
                    "الحل الفريد والميزة الاستثنائية التي يقدمها المنتج أو الخدمة للعميل لحل مشكلته والتي تميزه عن المنافسين",
                    "سعر البيع المكتوب على الفاتورة فقط",
                    "تكلفة إيجار المقر الإداري للشركة",
                    "الراتب الشهري للمدير التنفيذي"
                ],
                "answer": "الحل الفريد والميزة الاستثنائية التي يقدمها المنتج أو الخدمة للعميل لحل مشكلته والتي تميزه عن المنافسين",
                "explanation": "القيمة المقترحة هي السبب الجوهري الذي يدفع العميل لشراء المنتج واختياره بدلاً من منتجات الشركات المنافسة.",
                "topic": "ما هو نموذج العمل؟"
            },
            {
                "question": "ما هي الصناديق المتداولة في البورصة (ETFs) وما هي أهم ميزاتها للمستثمر الصغير؟",
                "options": [
                    "صناديق استثمارية تتبع مؤشراً معيناً وتتيح شراء سلة متنوعة من الأسهم بحصة واحدة ورسوم منخفضة وتداول لحظي كالأسهم",
                    "حسابات توفير بنكية تقليدية تعطي فائدة ثابتة بسيطة",
                    "شركات عقارية تبيع شققاً سكنية بالتقسيط فقط",
                    "صناديق خيرية تجمع التبرعات ولا تحقق أي عوائد مالية"
                ],
                "answer": "صناديق استثمارية تتبع مؤشراً معيناً وتتيح شراء سلة متنوعة من الأسهم بحصة واحدة ورسوم منخفضة وتداول لحظي كالأسهم",
                "explanation": "الصناديق المتداولة تمنح تنويعاً فورياً وتكلفة منخفضة وسهولة سيولة بالبيع والشراء خلال ساعات عمل السوق.",
                "topic": "أدوات الاستثمار"
            }
        ]

        for q in default_q:
            if not self.find_financial_answer(q["question"]):
                self.save_financial_question(
                    question_text=q["question"],
                    options=q["options"],
                    correct_answer=q["answer"],
                    explanation=q["explanation"],
                    topic=q.get("topic", "الثقافة المالية"),
                    user_id=0,
                    source="official_spx_seed",
                    sync_to_cloud=False
                )

    def get_financial_questions_count(self) -> int:
        """إجمالي عدد أسئلة الثقافة المالية التي تدرب عليها البوت"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM financial_literacy_bank")
                row = cursor.fetchone()
                return row["cnt"] if row else 0
        except Exception:
            return 0

    def search_financial_question(self, query: str) -> List[Dict[str, Any]]:
        """البحث في بنك أسئلة الثقافة المالية المطابقة"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM financial_literacy_bank WHERE question_text LIKE ? ORDER BY id DESC LIMIT 5",
                    (f"%{query}%",)
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []

    def get_recent_financial_questions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """جلب آخر الأسئلة المدربة في الثقافة المالية"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM financial_literacy_bank ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception:
            return []

    def sync_all_to_firebase(self) -> Dict[str, int]:
        """مزامنة ونقل جميع البيانات الموجودة في SQLite إلى Cloud Firestore"""
        stats = {"users": 0, "answers": 0, "chapters": 0, "finance": 0}
        if not self.firebase or not self.firebase.is_connected:
            logger.warning("تعذر تنفيذ المزامنة: الاتصال بـ Firebase غير مفعل أو غير متصل.")
            return stats

        with self._get_connection() as conn:
            # 1. حسابات الطلاب والمستخدمين
            users = conn.execute("SELECT * FROM bot_users").fetchall()
            for u in users:
                self.firebase.save_user_profile(
                    user_id=u["user_id"],
                    username=u["username"],
                    password=u["password"],
                    grade=u["grade"],
                    subject=u["subject"],
                    active_course_url=u["active_course_url"]
                )
                stats["users"] += 1

            # 2. بنك الإجابات النموذجية
            answers = conn.execute("SELECT * FROM saved_answers").fetchall()
            for a in answers:
                self.firebase.save_answer(
                    question_id=a["question_id"],
                    chapter_id=a["chapter_id"],
                    question_type=a["question_type"],
                    correct_choice_id=a["correct_choice_id"],
                    correct_content=a["correct_content"] or "",
                    model_answer=a["model_answer"] or "",
                    explanation=a["explanation"] or "",
                    question_text=a["question_text"] or ""
                )
                stats["answers"] += 1

            # 3. الفصول والتقدم
            chapters = conn.execute("SELECT * FROM saved_chapters").fetchall()
            for c in chapters:
                self.firebase.save_chapter(
                    chapter_id=c["chapter_id"],
                    course_id=c["course_id"],
                    seq=c["seq"],
                    name=c["name"],
                    url=c["url"],
                    test_type=c["test_type"],
                    question_count=c["question_count"],
                    completed=c["completed"],
                    diamond=c["diamond"]
                )
                stats["chapters"] += 1

            # 4. بنك الثقافة المالية
            fin_qs = conn.execute("SELECT * FROM financial_literacy_bank").fetchall()
            for f in fin_qs:
                try:
                    opts = json.loads(f["options_json"]) if f["options_json"] else []
                except Exception:
                    opts = []
                self.firebase.save_financial_question(
                    question_text=f["question_text"],
                    options=opts,
                    correct_answer=f["correct_answer"],
                    explanation=f["explanation"] or "",
                    topic=f["topic"] or "",
                    user_id=f["user_id"],
                    source=f["source"] or "training_image"
                )
                stats["finance"] += 1

        logger.info(f"✅ اكتملت المزامنة بنجاح إلى Firebase: {stats}")
        return stats

    # ==========================================
    # إدارة كلمات مرور الأدمن (Admin Passwords)
    # ==========================================

    def get_admin_passwords(self) -> List[str]:
        """جلب كلمات مرور الأدمن المعتمدة من فايربيس و SQLite مع ضمان بقاء 123 و 17890 دائماً"""
        base_passwords = ["123", "17890"]
        # محاولة الجلب السحابي من فايربيس أولاً
        if self.firebase and self.firebase.is_connected:
            fb_passes = self.firebase.get_admin_passwords()
            if fb_passes:
                merged = list(base_passwords)
                for p in fb_passes:
                    clean = str(p).strip()
                    if clean and clean not in merged:
                        merged.append(clean)
                try:
                    with self._get_connection() as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO admin_config (key, value) VALUES ('passwords', ?)",
                            (json.dumps(merged),)
                        )
                        conn.commit()
                except Exception:
                    pass
                return merged

        # البديل المحلي من SQLite
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM admin_config WHERE key = 'passwords'").fetchone()
            if row and row["value"]:
                try:
                    p_list = json.loads(row["value"])
                    if isinstance(p_list, list):
                        merged = list(base_passwords)
                        for p in p_list:
                            clean = str(p).strip()
                            if clean and clean not in merged:
                                merged.append(clean)
                        return merged
                except Exception:
                    pass
        return base_passwords

    def set_admin_passwords(self, passwords: List[str]) -> bool:
        """تحديث كلمات مرور الأدمن في SQLite وفايربيس"""
        str_passwords = [str(p).strip() for p in passwords if str(p).strip()]
        if not str_passwords:
            str_passwords = ["123", "17890"]

        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO admin_config (key, value) VALUES ('passwords', ?)",
                (json.dumps(str_passwords),)
            )
            conn.commit()

        if self.firebase and self.firebase.is_connected:
            self.firebase.set_admin_passwords(str_passwords)
        return True

    def add_admin_password(self, new_pass: str) -> bool:
        current = self.get_admin_passwords()
        clean = str(new_pass).strip()
        if clean and clean not in current:
            current.append(clean)
            return self.set_admin_passwords(current)
        return False

    def remove_admin_password(self, pass_to_remove: str) -> bool:
        current = self.get_admin_passwords()
        clean = str(pass_to_remove).strip()
        if clean in current and len(current) > 1:
            current.remove(clean)
            return self.set_admin_passwords(current)
        return False

    # ==========================================
    # باقات وخطط الاشتراك (Subscription Groups)
    # ==========================================

    def get_all_subscription_groups(self) -> List[Dict[str, Any]]:
        """جلب جميع الباقات مع عدد المشتركين في كل باقة (سحابياً من فايربيس أولاً)"""
        if self.firebase and self.firebase.is_connected:
            fb_groups = self.firebase.get_all_subscription_groups()
            if fb_groups is not None:
                try:
                    with self._get_connection() as conn:
                        for g in fb_groups:
                            gid = g.get("group_id")
                            if gid:
                                conn.execute("""
                                INSERT OR REPLACE INTO subscription_groups (group_id, password, tier_name, max_users, is_active)
                                VALUES (?, ?, ?, ?, ?)
                                """, (str(gid), str(g.get("password", "")), str(g.get("tier_name", "")), int(g.get("max_users", 0)), 1 if g.get("is_active", True) else 0))
                                for uid in g.get("joined_users", []):
                                    conn.execute("INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)", (str(gid), int(uid)))
                        conn.commit()
                except Exception:
                    pass
                return fb_groups

        groups = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM subscription_groups ORDER BY created_at DESC").fetchall()
            for r in rows:
                g_id = r["group_id"]
                members = conn.execute("SELECT user_id FROM group_members WHERE group_id = ?", (g_id,)).fetchall()
                joined = [m["user_id"] for m in members]
                comp_rows = conn.execute("SELECT student_username FROM completed_group_students WHERE group_id = ?", (g_id,)).fetchall()
                comp_list = [c["student_username"] for c in comp_rows]
                start_rows = conn.execute("SELECT student_username FROM group_started_students WHERE group_id = ?", (g_id,)).fetchall()
                start_list = [s["student_username"] for s in start_rows]
                groups.append({
                    "group_id": g_id,
                    "password": r["password"],
                    "tier_name": r["tier_name"],
                    "max_users": r["max_users"],
                    "is_active": bool(r["is_active"]),
                    "created_at": r["created_at"],
                    "joined_users": joined,
                    "users_count": len(joined),
                    "started_students": start_list,
                    "started_count": len(start_list),
                    "completed_students": comp_list,
                    "completed_count": len(comp_list)
                })
        return groups

    def get_subscription_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """جلب بيانات باقة محددة عبر معرفها (سحابياً من فايربيس أولاً)"""
        if self.firebase and self.firebase.is_connected:
            fb_g = self.firebase.get_subscription_group(group_id)
            if fb_g:
                return fb_g

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM subscription_groups WHERE group_id = ?", (group_id,)).fetchone()
            if not row:
                return None
            members = conn.execute("SELECT user_id FROM group_members WHERE group_id = ?", (group_id,)).fetchall()
            joined = [m["user_id"] for m in members]
            comp_rows = conn.execute("SELECT student_username FROM completed_group_students WHERE group_id = ?", (group_id,)).fetchall()
            comp_list = [c["student_username"] for c in comp_rows]
            start_rows = conn.execute("SELECT student_username FROM group_started_students WHERE group_id = ?", (group_id,)).fetchall()
            start_list = [s["student_username"] for s in start_rows]
            return {
                "group_id": row["group_id"],
                "password": row["password"],
                "tier_name": row["tier_name"],
                "max_users": row["max_users"],
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "joined_users": joined,
                "users_count": len(joined),
                "started_students": start_list,
                "started_count": len(start_list),
                "completed_students": comp_list,
                "completed_count": len(comp_list)
            }

    def save_subscription_group(
        self,
        group_id: str,
        password: str,
        tier_name: str,
        max_users: int,
        is_active: bool = True
    ) -> bool:
        """حفظ أو إنشاء باقة اشتراك جديدة"""
        with self._get_connection() as conn:
            conn.execute("""
            INSERT OR REPLACE INTO subscription_groups (group_id, password, tier_name, max_users, is_active)
            VALUES (?, ?, ?, ?, ?)
            """, (str(group_id), str(password), str(tier_name), int(max_users), 1 if is_active else 0))
            conn.commit()

        if self.firebase and self.firebase.is_connected:
            self.firebase.save_subscription_group(
                group_id=group_id,
                password=password,
                tier_name=tier_name,
                max_users=max_users,
                is_active=is_active
            )
        return True

    def delete_subscription_group(self, group_id: str) -> bool:
        """حذف باقة اشتراك بالكامل وأعضائها"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM subscription_groups WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
            conn.commit()

        if self.firebase and self.firebase.is_connected:
            self.firebase.delete_subscription_group(group_id)
        return True

    def toggle_subscription_group(self, group_id: str) -> bool:
        """تبديل حالة نشاط الباقة (تفعيل / تعطيل)"""
        g = self.get_subscription_group(group_id)
        if not g:
            return False
        new_status = not g["is_active"]
        with self._get_connection() as conn:
            conn.execute("UPDATE subscription_groups SET is_active = ? WHERE group_id = ?", (1 if new_status else 0, group_id))
            conn.commit()
        if self.firebase and self.firebase.is_connected:
            self.firebase.save_subscription_group(
                group_id=group_id,
                password=g["password"],
                tier_name=g["tier_name"],
                max_users=g["max_users"],
                is_active=new_status
            )
        return new_status

    def is_user_subscribed(self, user_id: int) -> bool:
        """التحقق هل المستخدم مشترك في أي باقة نشطة (سحابياً من فايربيس أولاً)"""
        if self.firebase and self.firebase.is_connected:
            sub = self.firebase.get_user_subscription(user_id)
            if sub:
                return True

        with self._get_connection() as conn:
            row = conn.execute("""
            SELECT m.group_id
            FROM group_members m
            JOIN subscription_groups g ON m.group_id = g.group_id
            WHERE m.user_id = ? AND g.is_active = 1
            LIMIT 1
            """, (int(user_id),)).fetchone()
            return row is not None

    def get_user_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """جلب تفاصيل اشتراك المستخدم والباقة التابع لها (سحابياً من فايربيس أولاً)"""
        if self.firebase and self.firebase.is_connected:
            sub = self.firebase.get_user_subscription(user_id)
            if sub:
                return sub

        with self._get_connection() as conn:
            row = conn.execute("""
            SELECT g.*, m.joined_at
            FROM group_members m
            JOIN subscription_groups g ON m.group_id = g.group_id
            WHERE m.user_id = ?
            ORDER BY m.joined_at DESC
            LIMIT 1
            """, (int(user_id),)).fetchone()
            if not row:
                return None
            members = conn.execute("SELECT user_id FROM group_members WHERE group_id = ?", (row["group_id"],)).fetchall()
            return {
                "group_id": row["group_id"],
                "tier_name": row["tier_name"],
                "max_users": row["max_users"],
                "joined_at": row["joined_at"],
                "is_active": bool(row["is_active"]),
                "current_count": len(members)
            }


    def record_completed_student(self, group_id: str, student_username: str, grade: str = "grade_1") -> Dict[str, Any]:
        """
        توثيق إكمال منصة طالب واحتسابه كعميل رسمي من باقة الوكيل في SQLite و Firebase.
        """
        clean_user = str(student_username).strip()
        newly_counted = False
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS completed_group_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                grade TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS group_started_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                user_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)
            exists = conn.execute(
                "SELECT 1 FROM completed_group_students WHERE group_id = ? AND student_username = ?",
                (group_id, clean_user)
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO completed_group_students (group_id, student_username, grade) VALUES (?, ?, ?)",
                    (group_id, clean_user, grade)
                )
                conn.commit()
                newly_counted = True

            comp_rows = conn.execute(
                "SELECT student_username FROM completed_group_students WHERE group_id = ?",
                (group_id,)
            ).fetchall()
            completed_cnt = len(comp_rows)

            grp = conn.execute("SELECT max_users, tier_name FROM subscription_groups WHERE group_id = ?", (group_id,)).fetchone()
            max_users = grp["max_users"] if grp else 25
            tier_name = grp["tier_name"] if grp else "باقة كيريو"

        if self.firebase and self.firebase.is_connected:
            try:
                self.firebase.record_completed_student(group_id, clean_user, grade=grade)
            except Exception as e_fb:
                logger.warning(f"Error recording completed student in Firebase: {e_fb}")

        return {
            "success": True,
            "newly_counted": newly_counted,
            "completed_count": completed_cnt,
            "max_users": max_users,
            "tier_name": tier_name
        }

    def get_user_group_id(self, user_id: int) -> Optional[str]:
        """جلب معرف الباقة المرتبط بها هذا المستخدم"""
        with self._get_connection() as conn:
            row = conn.execute("SELECT group_id FROM group_members WHERE user_id = ? ORDER BY joined_at DESC LIMIT 1", (int(user_id),)).fetchone()
            return row["group_id"] if row else None

    def verify_group_password(self, password: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        التحقق من صحة باسورد باقة الاشتراك وسعتها دون إضافة المستخدم رسمياً كعضو حتى يبدأ الحل.
        """
        clean_pass = str(password).strip()
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM subscription_groups WHERE password = ? OR group_id = ?",
                (clean_pass, clean_pass)
            ).fetchall()

            if not rows and ":" in clean_pass:
                gid, p = clean_pass.split(":", 1)
                rows = conn.execute(
                    "SELECT * FROM subscription_groups WHERE group_id = ? AND password = ?",
                    (gid.strip(), p.strip())
                ).fetchall()

            if not rows:
                return {"success": False, "reason": "invalid_password"}

            group = rows[0]
            g_id = group["group_id"]

            if not group["is_active"]:
                return {"success": False, "reason": "group_inactive", "group": dict(group)}

            max_cap = group["max_users"]
            conn.execute("""
            CREATE TABLE IF NOT EXISTS completed_group_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                grade TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS group_started_students (
                group_id TEXT NOT NULL,
                student_username TEXT NOT NULL,
                user_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, student_username)
            );
            """)
            comp_rows = conn.execute("SELECT student_username FROM completed_group_students WHERE group_id = ?", (g_id,)).fetchall()
            completed_cnt = len(comp_rows)
            if self.firebase and self.firebase.is_connected:
                cloud_g = self.firebase.get_subscription_group(g_id)
                if cloud_g and cloud_g.get("completed_count") is not None:
                    completed_cnt = max(completed_cnt, cloud_g.get("completed_count", 0))

            if completed_cnt >= max_cap:
                return {
                    "success": False,
                    "reason": "group_full",
                    "group": dict(group),
                    "current_count": completed_cnt,
                    "max_users": max_cap
                }

            return {
                "success": True,
                "group": dict(group),
                "current_count": completed_cnt,
                "max_users": max_cap
            }

    def add_user_to_subscription_group(self, group_id: str, user_id: int, student_username: Optional[str] = None) -> bool:
        """
        إضافة مستخدم وطالب إلى باقة اشتراك وتوثيق عضويته وبدء الحل محلياً وسحابياً.
        يتم استدعاء هذا الإجراء بمجرد ما يبدأ الحل الفعلي.
        """
        clean_g = str(group_id).strip()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO group_members (group_id, user_id) VALUES (?, ?)",
                (clean_g, int(user_id))
            )
            if student_username:
                clean_user = str(student_username).strip()
                conn.execute("""
                CREATE TABLE IF NOT EXISTS group_started_students (
                    group_id TEXT NOT NULL,
                    student_username TEXT NOT NULL,
                    user_id INTEGER,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (group_id, student_username)
                );
                """)
                conn.execute(
                    "INSERT OR REPLACE INTO group_started_students (group_id, student_username, user_id) VALUES (?, ?, ?)",
                    (clean_g, clean_user, int(user_id))
                )
            conn.commit()

        if self.firebase and self.firebase.is_connected:
            self.firebase.add_user_to_subscription_group(clean_g, int(user_id), student_username=student_username)
        return True

    def verify_and_join_group(self, user_id: int, password: str, auto_add: bool = False) -> Dict[str, Any]:
        """
        التحقق من كلمة مرور الباقة والسعة.
        إذا كان auto_add=True يتم الإضافة فوراً، وإذا كان False يتم فقط التحقق لتأجيل الإضافة إلى حين بدء الحل.
        """
        res = self.verify_group_password(password, user_id=user_id)
        if not res.get("success"):
            return res

        g_id = res["group"]["group_id"]
        if auto_add:
            self.add_user_to_subscription_group(g_id, int(user_id))

        return res


# نسخة عامة يمكن استيرادها مباشرة

    # ==========================================
    # تتبع النسخة التجريبية المجانية (أول 4 مستويات)
    # ==========================================

    def get_free_user_solved_count(self, user_id: int) -> int:
        """جلب عدد الفصول التي حلها المستخدم مجاناً في التجربة (سحابياً من فايربيس أولاً)"""
        if self.firebase and self.firebase.is_connected:
            fb_val = self.firebase.get_free_user_solved_count(user_id)
            if fb_val is not None:
                try:
                    with self._get_connection() as conn:
                        conn.execute("""
                        INSERT INTO free_user_trial (user_id, solved_count, last_chapter_seq, updated_at)
                        VALUES (?, ?, 0, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id) DO UPDATE SET
                            solved_count = excluded.solved_count,
                            updated_at = CURRENT_TIMESTAMP
                        """, (int(user_id), int(fb_val)))
                        conn.commit()
                except Exception:
                    pass
                return fb_val

        with self._get_connection() as conn:
            row = conn.execute("SELECT solved_count FROM free_user_trial WHERE user_id = ?", (int(user_id),)).fetchone()
            return row["solved_count"] if row else 0

    def increment_free_user_solved(self, user_id: int, chapter_seq: int = 0) -> int:
        """زيادة عدد الفصول المحلولة مجاناً للمستخدم وتوثيقها في SQLite وفايربيس"""
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO free_user_trial (user_id, solved_count, last_chapter_seq, updated_at)
            VALUES (?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                solved_count = solved_count + 1,
                last_chapter_seq = excluded.last_chapter_seq,
                updated_at = CURRENT_TIMESTAMP
            """, (int(user_id), int(chapter_seq)))
            conn.commit()
            row = conn.execute("SELECT solved_count FROM free_user_trial WHERE user_id = ?", (int(user_id),)).fetchone()
            cnt = row["solved_count"] if row else 1

        if self.firebase and self.firebase.is_connected:
            self.firebase.increment_free_user_solved(user_id, chapter_seq)
        return cnt

    def sync_to_firebase(self):
        """مزامنة كافة البيانات المحلية مع فايربيس سحابياً"""
        if self.firebase and self.firebase.is_connected:
            return self.firebase.sync_all_from_sqlite(self)
        return {"status": "error", "message": "Firebase is not connected"}


answers_db = AnswersDB()
