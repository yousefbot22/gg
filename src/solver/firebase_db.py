import logging
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger("FirebaseDB")

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("حزمة firebase-admin غير مثبتة. لن يتم تفعيل خدمات فايربيس.")


# مهلة الاستجابة القصوى لعمليات فايربيس السحابية لمنع أي تعليق
DEFAULT_TIMEOUT = 5.0


class FirebaseManager:
    """
    مدير الاتصال بقاعدة بيانات Cloud Firestore السحابية لحفظ ومزامنة:
    1. كلمات مرور ولوحة الأدمن (settings/admin)
    2. باقات وخطط الاشتراك والمجموعات (subscription_groups)
    3. اشتراكات ومجموعات المستخدمين (user_subscriptions)
    4. تتبع التجربة المجانية 4 فصول (free_trial_users)
    5. حسابات وجلسات المستخدمين (bot_users)
    6. بنك الإجابات المعتمدة (saved_answers)
    7. تقدم الفصول والدروس (saved_chapters)
    8. بنك أسئلة الثقافة المالية (financial_literacy_bank)
    """

    def __init__(self, cred_path: Optional[Path] = None):
        self.db = None
        self._initialized = False
        self._has_auth_error = False
        self.last_auth_error_message: Optional[str] = None
        self.cred_path = cred_path
        self._cred_mtime = 0.0
        self._init_firebase()

    def _init_firebase(self, force_reload: bool = False):
        """تهيئة الاتصال بفايربيس باستخدام ملف الخدمة الخاص"""
        if not FIREBASE_AVAILABLE:
            return

        cred = None
        # 1. فحص إمكانية تحميل الشهادة من متغير البيئة مباشرة (مفيد جداً للسيرفرات السحابية مثل blitz.cloud)
        raw_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON") or os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if raw_cred_json:
            try:
                import json
                cred_dict = json.loads(raw_cred_json.strip())
                cred = credentials.Certificate(cred_dict)
                logger.info("✅ تم تحميل شهادة اعتماد فايربيس من متغير البيئة (FIREBASE_CREDENTIALS_JSON)")
            except Exception as e_env_cred:
                logger.warning(f"تعذر قراءة شهادة فايربيس من متغير البيئة: {e_env_cred}")

        # 2. فحص ملف الشهادة الفعلي على القرص إذا لم تتوفر كمتغير بيئة
        if cred is None:
            if not self.cred_path or not self.cred_path.exists():
                # البحث عن أسماء ملفات شائعة في مجلد المشروع
                project_dir = Path(__file__).resolve().parent.parent
                potential_files = [
                    self.cred_path,
                    project_dir / "firebase_credentials.json",
                    project_dir / "serviceAccountKey.json",
                    project_dir / "firebase-adminsdk.json"
                ]
                found_path = None
                for p in potential_files:
                    if p and p.exists():
                        found_path = p
                        break

                if found_path:
                    self.cred_path = found_path
                else:
                    logger.info("ℹ️ لم يتم العثور على ملف مفتاح فايربيس (firebase_credentials.json). يعمل النظام بقاعدة البيانات المحلية (SQLite).")
                    return

            try:
                self._cred_mtime = self.cred_path.stat().st_mtime
                cred = credentials.Certificate(str(self.cred_path))
                logger.info(f"✅ تم تحميل مفتاح اعتماد فايربيس: {self.cred_path.name}")
            except Exception as e_file_cred:
                logger.warning(f"تعذر قراءة ملف شهادة فايربيس: {e_file_cred}")
                return

        try:
            if force_reload and firebase_admin._apps:
                for app_name in list(firebase_admin._apps.keys()):
                    try:
                        firebase_admin.delete_app(firebase_admin._apps[app_name])
                    except Exception:
                        pass

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            else:
                app = firebase_admin.get_app()
                cred = app.credential

            # فحص فوري وسريع للمصادقة للتحقق من صلاحية شهادة فايربيس ومنع أي تعليق في أزرار البوت
            try:
                import google.auth.transport.requests
                import threading
                gcred = cred.get_credential() if hasattr(cred, "get_credential") else None
                if gcred and hasattr(gcred, "refresh"):
                    refresh_err = []
                    def _do_refresh():
                        try:
                            req = google.auth.transport.requests.Request()
                            gcred.refresh(req)
                        except Exception as e_inner:
                            refresh_err.append(e_inner)

                    t = threading.Thread(target=_do_refresh, daemon=True)
                    t.start()
                    t.join(timeout=12.0)
                    if t.is_alive():
                        raise TimeoutError("مهلة فحص اعتماد فايربيس انتهت (12 ثانية)")
                    if refresh_err:
                        raise refresh_err[0]

                self.db = firestore.client()
                self._initialized = True
                self._has_auth_error = False
                self.last_auth_error_message = None
                logger.info("✅ تم التحقق من اتصال ومصادقة فايربيس بنجاح (Cloud Firestore Online).")
            except Exception as e_auth:
                err_str = str(e_auth).lower()
                self._has_auth_error = True
                self._initialized = False
                self.last_auth_error_message = str(e_auth)
                self.db = None
                logger.warning(
                    f"⚠️ [Firebase] تعذر مصادقة شهادة فايربيس مع خوادم Google ({e_auth}).\n"
                    f"   💡 تم تعطيل فايربيس تلقائياً والتحويل إلى قاعدة البيانات المحلية السريعة (SQLite: data/answers.db).\n"
                    f"   ✅ جميع أزرار وعمليات البوت تعمل الآن محلياً بنسبة 100% دون أي تعليق."
                )
        except Exception as e:
            logger.error(f"❌ خطأ أثناء تهيئة فايربيس: {e}")
            self._has_auth_error = True
            self.last_auth_error_message = str(e)
            self._initialized = False
            self.db = None

    def check_and_reload_if_modified(self) -> bool:
        """إعادة تحميل المفتاح والاتصال تلقائياً إذا قام المستخدم بتحديث أو استبدال ملف firebase_credentials.json"""
        if not FIREBASE_AVAILABLE or not self.cred_path or not self.cred_path.exists():
            return False
        try:
            mtime = self.cred_path.stat().st_mtime
            if mtime > self._cred_mtime or (self._has_auth_error and mtime != self._cred_mtime):
                logger.info("🔄 تم رصد تحديث في ملف مفتاح فايربيس! جاري إعادة الاتصال والمصادقة...")
                self._init_firebase(force_reload=True)
        except Exception:
            pass
        return self.is_connected

    def _handle_error(self, operation: str, error: Exception):
        """معالجة أخطاء فايربيس بذكاء وإيقاف المزامنة فوراً في حال مشاكل المصادقة أو انتهاء المهلة لمنع التعليق"""
        err_str = str(error).lower()
        is_auth_or_timeout = any(kw in err_str for kw in [
            "invalid_grant",
            "invalid jwt signature",
            "getting metadata from plugin failed",
            "unauthenticated",
            "permission_denied",
            "timeout",
            "deadline exceeded"
        ])

        if is_auth_or_timeout and not self._has_auth_error:
            self._has_auth_error = True
            self.last_auth_error_message = str(error)
            self._initialized = False
            logger.warning(
                f"⚠️ [Firebase Firestore] تعذر الاتصال بفايربيس أثناء '{operation}': {error}\n"
                f"   💡 السبب الشائع: عدم تطابق مفتاح الاعتماد أو عدم مزامنة وقت الجهاز (Invalid JWT Signature).\n"
                f"   🔄 تم التحويل تلقائياً وبأمان تام إلى قاعدة البيانات المحلية السريعة (SQLite).\n"
                f"   ✅ جميع العمليات والبيانات تعمل الآن محلياً بنسبة 100% بدون أي تعليق."
            )
        elif not is_auth_or_timeout:
            logger.error(f"خطأ أثناء {operation} في Firestore: {error}")

    @property
    def is_connected(self) -> bool:
        """التحقق من حالة الاتصال بفايربيس مع الفحص التلقائي لأي تحديث في ملف المفتاح"""
        if not self._initialized or self._has_auth_error:
            if self.cred_path and self.cred_path.exists():
                try:
                    if self.cred_path.stat().st_mtime > self._cred_mtime:
                        self.check_and_reload_if_modified()
                except Exception:
                    pass
        return self._initialized and self.db is not None and not self._has_auth_error

    def get_status_report(self) -> Dict[str, Any]:
        """تقرير تفصيلي عن حالة الاتصال السحابي بفايربيس والمفتاح المستخدم"""
        self.check_and_reload_if_modified()
        report = {
            "connected": self.is_connected,
            "project_id": "غير معروف",
            "client_email": "غير متوفر",
            "file_key_id": "غير متوفر",
            "file_exists": False,
            "error": self.last_auth_error_message or "لا يوجد أخطاء"
        }
        if self.cred_path and self.cred_path.exists():
            report["file_exists"] = True
            try:
                with open(self.cred_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    report["project_id"] = data.get("project_id", "غير محدد")
                    report["client_email"] = data.get("client_email", "غير محدد")
                    report["file_key_id"] = data.get("private_key_id", "غير محدد")
            except Exception as e:
                report["error"] = f"خطأ في قراءة ملف المفتاح: {e}"
        return report

    # ==========================================
    # إدارة المستخدمين (Users Collection)
    # ==========================================

    def save_user_profile(
        self,
        user_id: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        grade: Optional[str] = None,
        subject: Optional[str] = None,
        active_course_url: Optional[str] = None
    ) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("bot_users").document(str(user_id))
            data = {"user_id": user_id, "updated_at": firestore.SERVER_TIMESTAMP}
            if username is not None:
                data["username"] = username
            if password is not None:
                data["password"] = password
            if grade is not None:
                data["grade"] = grade
            if subject is not None:
                data["subject"] = subject
            if active_course_url is not None:
                data["active_course_url"] = active_course_url

            doc_ref.set(data, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.debug(f"✅ [Firestore] تم حفظ بيانات المستخدم ({user_id}) سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error(f"حفظ المستخدم ({user_id})", e)
            return False

    def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("bot_users").document(str(user_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            self._handle_error(f"جلب بيانات المستخدم ({user_id})", e)
        return None

    def clear_user_credentials(self, user_id: int) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("bot_users").document(str(user_id))
            doc_ref.set({
                "username": None,
                "password": None,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            return True
        except Exception as e:
            self._handle_error(f"مسح بيانات المستخدم ({user_id})", e)
            return False

    # ==========================================
    # إدارة الإجابات النموذجية (Saved Answers)
    # ==========================================

    def save_answer(
        self,
        question_id: int,
        chapter_id: int,
        question_type: str,
        correct_choice_id: Optional[int] = None,
        correct_content: str = "",
        model_answer: str = "",
        explanation: str = "",
        question_text: str = ""
    ) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("saved_answers").document(str(question_id))
            payload = {
                "question_id": question_id,
                "chapter_id": chapter_id,
                "question_type": question_type,
                "correct_choice_id": correct_choice_id,
                "correct_content": correct_content,
                "model_answer": model_answer,
                "explanation": explanation,
                "question_text": question_text,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            doc_ref.set(payload, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.debug(f"✅ [Firestore] تم حفظ الإجابة للسؤال ({question_id}) سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error(f"حفظ الإجابة ({question_id})", e)
            return False

    def get_answer(self, question_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("saved_answers").document(str(question_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            self._handle_error(f"جلب الإجابة ({question_id})", e)
        return None

    # ==========================================
    # بنك الثقافة المالية (Financial Literacy Bank)
    # ==========================================

    def save_financial_question(
        self,
        question_text: str,
        options: List[str],
        correct_answer: str,
        explanation: str = "",
        topic: str = "",
        user_id: Optional[int] = None,
        source: str = "training_image"
    ) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_id = str(hash(question_text.strip()))
            doc_ref = self.db.collection("financial_literacy_bank").document(doc_id)
            doc_ref.set({
                "question_text": question_text,
                "options": options,
                "correct_answer": correct_answer,
                "explanation": explanation,
                "topic": topic,
                "user_id": user_id,
                "source": source,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.debug(f"✅ [Firestore] تم حفظ سؤال الثقافة المالية سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error("حفظ سؤال الثقافة المالية", e)
            return False

    def get_all_financial_questions(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            docs = self.db.collection("financial_literacy_bank").stream(timeout=DEFAULT_TIMEOUT)
            return [d.to_dict() for d in docs]
        except Exception as e:
            self._handle_error("جلب أسئلة الثقافة المالية", e)
            return []

    # ==========================================
    # إدارة الفصول (Chapters)
    # ==========================================

    def save_chapter(
        self,
        chapter_id: int,
        course_id: str,
        seq: int,
        name: str,
        url: str,
        test_type: str,
        question_count: int = 0,
        completed: int = 0,
        diamond: int = 0
    ) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("saved_chapters").document(str(chapter_id))
            doc_ref.set({
                "chapter_id": chapter_id,
                "course_id": course_id,
                "seq": seq,
                "name": name,
                "url": url,
                "test_type": test_type,
                "question_count": question_count,
                "completed": completed,
                "diamond": diamond,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.debug(f"✅ [Firestore] تم حفظ الفصل ({chapter_id}) سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error(f"حفظ الفصل ({chapter_id})", e)
            return False

    def update_chapter_progress(self, chapter_id: int, completed: int = 1, diamond: int = 5) -> bool:
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("saved_chapters").document(str(chapter_id))
            doc_ref.set({
                "completed": completed,
                "diamond": diamond,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.debug(f"✅ [Firestore] تم تحديث تقدم الفصل ({chapter_id}) سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error(f"تحديث تقدم الفصل ({chapter_id})", e)
            return False

    # ==========================================
    # إعدادات الأدمن وباقات الاشتراك (Admin & Subscription Groups)
    # ==========================================

    def get_admin_passwords(self) -> Optional[List[str]]:
        """جلب كلمات مرور الأدمن من فايربيس (المسار: settings/admin)"""
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("settings").document("admin")
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if doc.exists:
                data = doc.to_dict() or {}
                passwords = data.get("passwords")
                if isinstance(passwords, list):
                    return [str(p) for p in passwords]
                elif isinstance(passwords, str):
                    return [passwords]
            else:
                default_passwords = ["123", "17890"]
                doc_ref.set({
                    "passwords": default_passwords,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True, timeout=DEFAULT_TIMEOUT)
                return default_passwords
        except Exception as e:
            self._handle_error("جلب كلمات مرور الأدمن", e)
        return None

    def set_admin_passwords(self, passwords: List[str]) -> bool:
        """تحديث كلمات مرور الأدمن في فايربيس"""
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("settings").document("admin")
            doc_ref.set({
                "passwords": passwords,
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.info("✅ [Firestore] تم تحديث كلمات مرور الأدمن سحابياً.")
            return True
        except Exception as e:
            self._handle_error("تحديث كلمات مرور الأدمن", e)
            return False

    def get_all_subscription_groups(self) -> Optional[List[Dict[str, Any]]]:
        """جلب جميع مجموعات وباقات الاشتراك من فايربيس"""
        if not self.is_connected:
            return None
        try:
            groups_ref = self.db.collection("subscription_groups")
            docs = groups_ref.stream(timeout=DEFAULT_TIMEOUT)
            groups = []
            for d in docs:
                g = d.to_dict() or {}
                g["group_id"] = d.id
                groups.append(g)
            return groups
        except Exception as e:
            self._handle_error("جلب مجموعات الاشتراك", e)
            return None

    def get_subscription_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """جلب بيانات باقة اشتراك محددة"""
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("subscription_groups").document(str(group_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if doc.exists:
                g = doc.to_dict() or {}
                g["group_id"] = doc.id
                return g
        except Exception as e:
            self._handle_error(f"جلب باقة الاشتراك ({group_id})", e)
        return None

    def save_subscription_group(
        self,
        group_id: str,
        password: str,
        tier_name: str,
        max_users: int,
        is_active: bool = True
    ) -> bool:
        """حفظ أو تحديث باقة اشتراك في فايربيس"""
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("subscription_groups").document(str(group_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            existing = doc.to_dict() if doc.exists else {}
            joined_users = existing.get("joined_users", [])
            completed_students = existing.get("completed_students", [])

            data = {
                "group_id": str(group_id),
                "password": str(password),
                "tier_name": str(tier_name),
                "max_users": int(max_users),
                "is_active": bool(is_active),
                "joined_users": joined_users,
                "users_count": len(joined_users),
                "completed_students": completed_students,
                "completed_count": len(completed_students),
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            if not doc.exists:
                data["created_at"] = firestore.SERVER_TIMESTAMP

            doc_ref.set(data, merge=True, timeout=DEFAULT_TIMEOUT)
            logger.info(f"✅ [Firestore] تم حفظ باقة الاشتراك ({group_id}) سحابياً بنجاح.")
            return True
        except Exception as e:
            self._handle_error(f"حفظ باقة الاشتراك ({group_id})", e)
            return False

    def delete_subscription_group(self, group_id: str) -> bool:
        """حذف باقة اشتراك من فايربيس"""
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("subscription_groups").document(str(group_id))
            doc_ref.delete(timeout=DEFAULT_TIMEOUT)
            logger.info(f"✅ [Firestore] تم حذف باقة الاشتراك ({group_id}) سحابياً.")
            return True
        except Exception as e:
            self._handle_error(f"حذف باقة الاشتراك ({group_id})", e)
            return False

    def add_user_to_subscription_group(self, group_id: str, user_id: int, student_username: Optional[str] = None) -> bool:
        """إضافة مستخدم إلى باقة اشتراك في فايربيس مع توثيق حسابه في مجموعات المشتركين وبدء الحل"""
        if not self.is_connected:
            return False
        try:
            doc_ref = self.db.collection("subscription_groups").document(str(group_id))
            update_data = {
                "joined_users": firestore.ArrayUnion([int(user_id)]),
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            if student_username:
                clean_u = str(student_username).strip()
                if clean_u:
                    update_data["started_students"] = firestore.ArrayUnion([clean_u])

            doc_ref.set(update_data, merge=True, timeout=DEFAULT_TIMEOUT)

            # توثيق في جدول اشتراكات المستخدمين لسرعة الفحص المباشر
            sub_doc = {
                "user_id": int(user_id),
                "group_id": str(group_id),
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            if student_username:
                sub_doc["student_username"] = str(student_username).strip()
            self.db.collection("user_subscriptions").document(str(user_id)).set(
                sub_doc,
                merge=True,
                timeout=DEFAULT_TIMEOUT
            )
            return True
        except Exception as e:
            self._handle_error(f"إضافة مستخدم ({user_id}) للباقة ({group_id})", e)
            return False


    def record_completed_student(self, group_id: str, student_username: str, grade: str = "grade_1") -> Dict[str, Any]:
        """
        توثيق إكمال منصة طالب بالكامل 100% واحتسابه كعميل رسمي من باقة الوكيل في فايربيس.
        """
        if not self.is_connected:
            return {"success": False, "reason": "not_connected"}
        try:
            doc_ref = self.db.collection("subscription_groups").document(str(group_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if not doc.exists:
                return {"success": False, "reason": "group_not_found"}

            data = doc.to_dict() or {}
            completed = list(data.get("completed_students", []))
            max_users = data.get("max_users", 25)
            clean_username = str(student_username).strip()

            newly_counted = False
            if clean_username not in completed:
                completed.append(clean_username)
                newly_counted = True
                doc_ref.set({
                    "completed_students": firestore.ArrayUnion([clean_username]),
                    "completed_count": len(completed),
                    "updated_at": firestore.SERVER_TIMESTAMP
                }, merge=True, timeout=DEFAULT_TIMEOUT)

            return {
                "success": True,
                "newly_counted": newly_counted,
                "completed_count": len(completed),
                "max_users": max_users,
                "tier_name": data.get("tier_name", "باقة كيريو")
            }
        except Exception as e:
            self._handle_error(f"توثيق عميل مكتمل ({group_id})", e)
            return {"success": False, "reason": str(e)}

    def get_user_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """التحقق من اشتراك المستخدم وباقته من فايربيس مباشرة"""
        if not self.is_connected:
            return None
        try:
            # 1. فحص مباشر في كوليكشن user_subscriptions
            user_doc = self.db.collection("user_subscriptions").document(str(user_id)).get(timeout=DEFAULT_TIMEOUT)
            if user_doc.exists:
                u_data = user_doc.to_dict() or {}
                gid = u_data.get("group_id")
                if gid:
                    grp = self.get_subscription_group(gid)
                    if grp and grp.get("is_active", True):
                        return {
                            "group_id": gid,
                            "tier_name": grp.get("tier_name", "باقة كيريو"),
                            "max_users": grp.get("max_users", 0),
                            "joined_at": u_data.get("joined_at", ""),
                            "is_active": True,
                            "current_count": grp.get("users_count", len(grp.get("joined_users", [])))
                        }

            # 2. فحص بالاستعلام في كوليكشن subscription_groups
            groups_ref = self.db.collection("subscription_groups")
            query = groups_ref.where("joined_users", "array_contains", int(user_id)).where("is_active", "==", True).limit(1)
            docs = list(query.stream(timeout=DEFAULT_TIMEOUT))
            if docs:
                g = docs[0].to_dict() or {}
                g["group_id"] = docs[0].id
                joined = g.get("joined_users", [])
                return {
                    "group_id": g["group_id"],
                    "tier_name": g.get("tier_name", "باقة كيريو"),
                    "max_users": g.get("max_users", 0),
                    "joined_at": "",
                    "is_active": True,
                    "current_count": len(joined)
                }
        except Exception as e:
            self._handle_error(f"جلب اشتراك المستخدم ({user_id})", e)
        return None

    # ==========================================
    # تتبع النسخة التجريبية المجانية (أول 4 مستويات)
    # ==========================================

    def get_free_user_solved_count(self, user_id: int) -> Optional[int]:
        """جلب عدد المستويات المحلولة مجاناً للمستخدم من فايربيس"""
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("free_trial_users").document(str(user_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            if doc.exists:
                return int(doc.to_dict().get("solved_count", 0))
            return 0
        except Exception as e:
            self._handle_error(f"جلب عداد التجربة المجانية ({user_id})", e)
            return None

    def increment_free_user_solved(self, user_id: int, chapter_seq: int = 0) -> Optional[int]:
        """تسجيل وزيادة عدد المستويات المحلولة للمستخدم المجاني في فايربيس"""
        if not self.is_connected:
            return None
        try:
            doc_ref = self.db.collection("free_trial_users").document(str(user_id))
            doc = doc_ref.get(timeout=DEFAULT_TIMEOUT)
            cur_count = 0
            if doc.exists:
                cur_count = int(doc.to_dict().get("solved_count", 0))
            new_count = cur_count + 1
            doc_ref.set({
                "user_id": int(user_id),
                "solved_count": new_count,
                "last_chapter_seq": int(chapter_seq),
                "updated_at": firestore.SERVER_TIMESTAMP
            }, merge=True, timeout=DEFAULT_TIMEOUT)
            return new_count
        except Exception as e:
            self._handle_error(f"تحديث عداد التجربة المجانية ({user_id})", e)
            return None

    # ==========================================
    # المزامنة السحابية الشاملة (Cloud Sync All Data)
    # ==========================================

    def sync_all_from_sqlite(self, answers_db) -> Dict[str, Any]:
        """
        مزامنة سحابية شاملة تدفع كافة البيانات من SQLite المحلي إلى Firestore:
        - كلمات مرور الأدمن (settings/admin)
        - كافة باقات الاشتراك ومستخدميها (subscription_groups)
        - مستخدمي التجربة المجانية (free_trial_users)
        - حسابات وجلسات الطلاب (bot_users)
        """
        if not self.is_connected:
            return {"status": "error", "message": "Firebase is not connected"}

        stats = {"admin": 0, "groups": 0, "trials": 0, "users": 0}
        try:
            # 1. مزامنة كلمات مرور الأدمن
            admin_passes = answers_db.get_admin_passwords()
            if admin_passes:
                self.set_admin_passwords(admin_passes)
                stats["admin"] = len(admin_passes)

            # 2. مزامنة باقات ومجموعات الاشتراك
            groups = answers_db.get_all_subscription_groups()
            for g in groups:
                self.save_subscription_group(
                    group_id=g["group_id"],
                    password=g["password"],
                    tier_name=g["tier_name"],
                    max_users=g["max_users"],
                    is_active=g["is_active"]
                )
                for uid in g.get("joined_users", []):
                    self.add_user_to_subscription_group(g["group_id"], uid)
                stats["groups"] += 1

            # 3. مزامنة بيانات التجربة المجانية والطلاب
            with answers_db._get_connection() as conn:
                trials = conn.execute("SELECT * FROM free_user_trial").fetchall()
                for t in trials:
                    self.db.collection("free_trial_users").document(str(t["user_id"])).set({
                        "user_id": t["user_id"],
                        "solved_count": t["solved_count"],
                        "last_chapter_seq": t["last_chapter_seq"],
                        "updated_at": firestore.SERVER_TIMESTAMP
                    }, merge=True, timeout=DEFAULT_TIMEOUT)
                    stats["trials"] += 1

                users = conn.execute("SELECT * FROM bot_users").fetchall()
                for u in users:
                    self.db.collection("bot_users").document(str(u["user_id"])).set({
                        "user_id": u["user_id"],
                        "grade": u["grade"],
                        "subject": u["subject"],
                        "active_course_url": u["active_course_url"],
                        "updated_at": firestore.SERVER_TIMESTAMP
                    }, merge=True, timeout=DEFAULT_TIMEOUT)
                    stats["users"] += 1

            logger.info(f"✅ تم الانتهاء من المزامنة السحابية الشاملة إلى Firestore بنجاح: {stats}")
            return {"status": "success", "stats": stats}
        except Exception as e:
            logger.error(f"❌ خطأ أثناء المزامنة الشاملة إلى فايربيس: {e}")
            return {"status": "error", "message": str(e), "stats": stats}
