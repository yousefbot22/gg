import os
import json
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from PIL import Image


class GeminiSolver:
    """مساعد الذكاء الاصطناعي لحل تمارين وكويزات منصة كيريو البرمجية"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.client = None
        # قائمة النماذج حسب التوفر والسرعة العالية
        self.preferred_models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.8-flash"
        ]
        if self.api_key:
            self._init_client()

    def set_api_key(self, api_key: str):
        """تحديث مفتاح API ديناميكياً"""
        self.api_key = api_key.strip()
        self._init_client()

    def _init_client(self):
        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"Error initializing Gemini client: {e}")
            self.client = None

    def is_configured(self) -> bool:
        return bool(
            self.client
            and self.api_key
            and self.api_key != "YOUR_GEMINI_API_KEY_HERE"
            and len(self.api_key) > 15
        )

    async def generate_response(self, prompt: str) -> str:
        """توليد رد نصي عام من Gemini لأي سؤال أو استفسار تعليمي"""
        if not self.is_configured():
            return ""
        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[prompt]
                )
                if response and response.text:
                    return response.text.strip()
            except Exception:
                continue
        return ""

    async def solve_code_task(
        self,
        instruction: str,
        current_code: str = "",
        language: str = "python",
        screenshot_path: Optional[str] = None
    ) -> str:
        """حل تمرين برمجي (بايثون أو جافاسكريبت) بناءً على التعليمات والصورة"""
        if not self.is_configured():
            raise ValueError("مفتاح Gemini API غير معين! يرجى إدخال المفتاح أولاً.")

        prompt = f"""
أنت خبير برمجي في منصة Qureo التعليمية.
المهمة: حل التمرين البرمجي بلغة ({language}).

التعليمات المطلوبة من الطالب:
{instruction}

الكود الموجود حالياً في المحرر (إن وجد):
```{language}
{current_code}
```

المطلوب:
1. اكتب الكود الكامل أو التعديل المطلوب بدقة 100% ليجتاز الاختبار.
2. لا تكتب أي شرح أو مقدمات إطلاقاً.
3. اكتب الكود البرمجي فقط داخل صيغة كود نظيفة بدون أي كلام زائد، لأن الكود سيتم نسخه ولصقه في المحرر آلياً.
"""
        contents: List[Any] = [prompt]

        if screenshot_path and Path(screenshot_path).exists():
            try:
                with open(screenshot_path, "rb") as f:
                    img_bytes = f.read()
                part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                contents.append(part)
            except Exception as e:
                print(f"Warning: could not load image {screenshot_path}: {e}")

        # محاولة الاستدعاء بالنماذج المتاحة
        last_error = None
        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                if response and response.text:
                    cleaned_code = self._clean_code_output(response.text)
                    return cleaned_code
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f"فشل استدعاء Gemini: {last_error}")

    async def solve_quiz_question(
        self,
        question: str,
        options: List[str],
        screenshot_path: Optional[str] = None
    ) -> int:
        """حل سؤال اختيار من متعدد وتحديد رقم الخيار الصحيح (0-indexed)"""
        if not self.is_configured():
            raise ValueError("مفتاح Gemini API غير معين! يرجى إدخال المفتاح أولاً.")

        options_text = "\n".join([f"{i}. {opt}" for i, opt in enumerate(options)])
        prompt = f"""
أنت مساعد ذكي لحل اختبارات منصة Qureo التعليمية.
أجب عن سؤال الاختيار من متعدد التالي باختيار رقم الإجابة الصحيحة فقط (0, 1, 2, ...):

السؤال:
{question}

الخيارات المتاحة:
{options_text}

المطلوب منك إرجاع كائن JSON فقط بالصيغة التالية:
{{"correct_index": 0, "reason": "شرح سريع باللغة العربية"}}
"""
        contents: List[Any] = [prompt]

        if screenshot_path and Path(screenshot_path).exists():
            try:
                with open(screenshot_path, "rb") as f:
                    img_bytes = f.read()
                part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                contents.append(part)
            except Exception as e:
                print(f"Warning: could not load image {screenshot_path}: {e}")

        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                if response and response.text:
                    text = response.text.strip()
                    # استخراج JSON من الرد
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        idx = int(data.get("correct_index", 0))
                        if 0 <= idx < len(options):
                            return idx
                    # إذا لم يكن JSON صريحاً، ابحث عن رقم
                    digits = re.findall(r'\d+', text)
                    if digits:
                        d = int(digits[0])
                        if 0 <= d < len(options):
                            return d
                    return 0
            except Exception as e:
                continue

        return 0

    async def analyze_screen_and_guide(
        self,
        screenshot_path: str,
        additional_context: str = ""
    ) -> Dict[str, Any]:
        """تحليل لقطة شاشة من منصة Qureo لفهم حالة الشاشة والخطوة التالية"""
        if not self.is_configured():
            raise ValueError("مفتاح Gemini API غير معين.")

        if not Path(screenshot_path).exists():
            return {"error": "Screenshot file does not exist"}

        prompt = f"""
أنت المساعد الذكي الآلي لمنصة Qureo التعليمية للبرمجة (Python / JavaScript).
السياق الإضافي للنصوص في الصفحة: {additional_context}

حلل لقطة الشاشة بدقة عالية وأخبرني:
1. نوع الصفحة الحالية ("page_type"):
   - "chapter_map": قائمة الفصول والدروس (مثل شاشة اختيار الفصل 3 وبطاقات الدروس مثل 'إسناد القيم إلى المتغيرات' أو 'التدرب على المتغيرات').
   - "dashboard": الشاشة الرئيسية للمسار التي تحتوي على زر 'بدء التعلم' أو 'ابدأ'.
   - "code_task": شاشة تمرين برمجي ومحرر كود لتنفيذ المطلوب وتشغيله.
   - "quiz": سؤال اختيار من متعدد (اختبار الفهم).
   - "dialogue": حوار لشخصية الروبوت أو نافذة تعليمات تتطلب الضغط على 'التالي' أو النقر للمتابعة.
   - "completed": نافذة إكمال المستوى بنجاح وظهور عبارات مثل 'أحسنت' أو 'تهانينا' أو 'المستوى التالي'.
2. إذا كانت شاشة قائمة الدروس (chapter_map):
   - حدد اسم الدرس التالي غير المكتمل (الذي لا توجد بجانبه علامة صح رمادية أو خضراء ✓) وضعه في "next_button" بدقة.
3. إذا كانت شاشة تمرين كود (code_task):
   - اكتب الكود البرمجي الصحيح 100% المطلوب وضعه في المحرر في "solution_code".
   - حدد زر التشغيل ("تشغيل") في "next_button".
4. ما هو الزر المطلوب النقر عليه للانتقال للخطوة التالية في "next_button"؟

أرجع النتيجة بصيغة JSON فقط:
{{
    "page_type": "chapter_map | code_task | dashboard | quiz | dialogue | completed | unknown",
    "summary": "ملخص باللغة العربية للوضع الحالي في الشاشة",
    "solution_code": "الكود المقترح إن وجد أو null",
    "next_button": "اسم الزر أو الدرس المطلوب النقر عليه إن وجد أو null",
    "is_passed": true/false
}}
"""
        contents: List[Any] = [prompt]
        if screenshot_path and Path(screenshot_path).exists():
            try:
                with open(screenshot_path, "rb") as f:
                    img_bytes = f.read()
                part = types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                contents.append(part)
            except Exception as e:
                print(f"Warning loading screenshot in analyze: {e}")

        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                if response and response.text:
                    text = response.text.strip()
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    return {"summary": text, "page_type": "unknown"}
            except Exception as e:
                continue

        return {"error": "تعذر تحليل الشاشة عبر الذكاء الاصطناعي"}

    def _clean_code_output(self, text: str) -> str:
        """تنظيف الكود المرتجع من أي نصوص أو markdown زائدة"""
        text = text.strip()
        # إزالة وسوم الماركدوان ```python ... ```
        if "```" in text:
            pattern = r"```(?:python|javascript|js)?\n?(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return text

    async def solve_financial_literacy_image(
        self,
        image_path: str,
        additional_prompt: str = ""
    ) -> Dict[str, Any]:
        """
        تحليل وحل سؤال من منصة الثقافة المالية من صورة أو لقطة شاشة مرسلة بالذكاء الاصطناعي
        تستخرج نص السؤال، الخيارات، الإجابة الصحيحة بدقة 100% مع التفسير العلمي المالي
        """
        if not self.is_configured():
            raise ValueError("مفتاح Gemini API غير معين! يرجى إدخال المفتاح أولاً.")

        if not Path(image_path).exists():
            return {"error": "ملف الصورة غير موجود"}

        prompt = f"""
أنت معلم وخبير معتمد في مادة "الثقافة المالية" (Financial Literacy) لطلاب المرحلة الثانوية (الصف الثاني الثانوي).
المطلوب منك:
1. قراءة وتحليل صورة السؤال المالي المرفقة بدقة بالغة.
2. استخراج نص السؤال كاملاً كما هو باللغة العربية.
3. استخراج جميع الخيارات أو البدائل المتاحة (A, B, C, D أو 1, 2, 3, 4).
4. تحديد الإجابة الصحيحة 100% وفق المناهج التعليمية للثقافة المالية (المفاهيم: الميزانية الشخصية، الادخار، الاستثمار، البنوك، الشيكات، المعاملات الإلكترونية، بطاقات الائتمان، إدارة الديون، التضخم، حقوق المستهلك).
5. كتابة شرح وتفسير مالي مبسط يوضح سبب اختيار هذه الإجابة.
{additional_prompt}

أرجع النتيجة بصيغة JSON فقط:
{{
    "question": "نص السؤال المستخرج بدقة",
    "options": ["الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع"],
    "correct_index": 0,
    "correct_answer": "نص الإجابة الصحيحة الكامل",
    "explanation": "شرح وتفسير تعليمي يوضح لماذا هذه الإجابة هي الصحيحة",
    "topic": "الموضوع المالي (مثال: الادخار / الاستثمار / البنوك / الميزانية)"
}}
"""
        contents: List[Any] = [prompt]
        try:
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            # استنتاج نوع MIME للصورة
            mime_type = "image/jpeg" if str(image_path).lower().endswith((".jpg", ".jpeg")) else "image/png"
            part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            contents.append(part)
        except Exception as e:
            return {"error": f"تعذر قراءة الصورة: {str(e)}"}

        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents
                )
                if response and response.text:
                    text = response.text.strip()
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        return data
                    return {
                        "question": "سؤال مستخرج من الصورة",
                        "options": [],
                        "correct_answer": text,
                        "explanation": text,
                        "topic": "ثقافة مالية"
                    }
            except Exception:
                continue

        return {"error": "تعذر تحليل السؤال المالي عبر الذكاء الاصطناعي"}

    async def solve_financial_literacy_text(
        self,
        question: str,
        options: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """حل سؤال ثقافة مالية نصي بالذكاء الاصطناعي مع الشرح والتحليل"""
        if not self.is_configured():
            raise ValueError("مفتاح Gemini API غير معين! يرجى إدخال المفتاح أولاً.")

        options_str = "\n".join([f"- {opt}" for opt in options]) if options else "لا توجد خيارات محددة"
        prompt = f"""
أنت معلم وخبير في مادة "الثقافة المالية" للصف الثاني الثانوي.
أجب عن السؤال التالي بدقة متناهية:

السؤال:
{question}

الخيارات إن وجدت:
{options_str}

أرجع الإجابة الصحيحة وشرحاً وافياً ومختصراً باللغة العربية بصيغة JSON:
{{
    "correct_answer": "الإجابة الصحيحة النموذجية",
    "explanation": "تفسير مالي علمي مبسط",
    "topic": "الموضوع المالي"
}}
"""
        for model_name in self.preferred_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[prompt]
                )
                if response and response.text:
                    text = response.text.strip()
                    match = re.search(r'\{.*\}', text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    return {
                        "correct_answer": text,
                        "explanation": "تم الحل بواسطة الذكاء الاصطناعي",
                        "topic": "ثقافة مالية"
                    }
            except Exception:
                continue

        return {"correct_answer": "تعذر استخراج الإجابة", "explanation": "", "topic": "ثقافة مالية"}
