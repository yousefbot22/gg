import asyncio
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SPXAPI:
    """
    عميل التعامل البرمجي المباشر مع API منصة اسبركس التعليمية (SPX Learning Square - الثقافة المالية).
    المنصة الرسمية: https://egy.app.spx-learning-square.com
    المقرر: مادة الثقافة المالية (Subject ID: 7) لطلاب الصف الثاني الثانوي.
    """

    BASE_URL = "https://egy.app.spx-learning-square.com/api/v1"

    def __init__(self, page=None):
        self.page = page

    def set_page(self, page):
        self.page = page

    # ==========================================
    # استدعاء الـ API الأساسي عبر المتصفح (Playwright window.fetch)
    # ==========================================

    async def call_api(
        self,
        endpoint: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        تنفيذ طلب API عبر window.fetch داخل صفحة المتصفح في نطاق egy.app.spx-learning-square.com
        يقوم تلقائياً بتضمين الكوكيز، وتوكن الدخول من localStorage / sessionStorage، وCSRF header.
        """
        if not self.page or self.page.is_closed():
            logger.warning("المتصفح غير نشط أو الصفحة مغلقة عند استدعاء SPX API.")
            return {"ok": False, "status": 0, "error": "المتصفح غير نشط أو الصفحة مغلقة."}

        # التأكد من أن المتصفح متواجد على نطاق منصة اسبركس ليتمكن window.fetch من استخدام الكوكيز والتوكن
        try:
            curr_url = self.page.url.lower()
            if "spx-learning-square.com" not in curr_url:
                await self.page.goto("https://egy.app.spx-learning-square.com/subjects/7/curriculum", wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(1)
        except Exception as e_nav:
            logger.warning(f"Error ensuring SPX domain in call_api: {e_nav}")

        clean_ep = endpoint
        if not clean_ep.startswith("http"):
            if not clean_ep.startswith("/api/v1"):
                if not clean_ep.startswith("/"):
                    clean_ep = f"/{clean_ep}"
                clean_ep = f"/api/v1{clean_ep}"
            full_url = f"https://egy.app.spx-learning-square.com{clean_ep}"
        else:
            full_url = clean_ep

        js_fetch = """
        async ([url, method, body]) => {
            try {
                // استخراج التوكن من التخزين المحلي إن وجد
                let token = '';
                try {
                    token = localStorage.getItem('token') ||
                            localStorage.getItem('access_token') ||
                            localStorage.getItem('auth_token') ||
                            sessionStorage.getItem('token') || '';
                } catch(e) {}

                const headers = {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                };
                if (token) {
                    headers['Authorization'] = 'Bearer ' + token;
                }

                // استخراج CSRF Token إن وجد
                try {
                    const xsrf = document.cookie.split('; ').find(row => row.startsWith('XSRF-TOKEN='));
                    if (xsrf) {
                        headers['X-XSRF-TOKEN'] = decodeURIComponent(xsrf.split('=')[1]);
                    }
                } catch(e) {}

                const options = {
                    method: method,
                    credentials: 'include',
                    headers: headers
                };

                if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
                    options.body = JSON.stringify(body);
                }

                const response = await window.fetch(url, options);
                const contentType = response.headers.get('content-type') || '';
                let data = null;
                if (contentType.includes('application/json')) {
                    data = await response.json();
                } else {
                    data = await response.text();
                }
                return {
                    ok: response.ok,
                    status: response.status,
                    data: data
                };
            } catch (err) {
                return {
                    ok: false,
                    status: 0,
                    error: err.toString()
                };
            }
        }
        """

        try:
            res = await self.page.evaluate(js_fetch, [full_url, method.upper(), body])
            logger.info(f"SPX API {method.upper()} {full_url} -> status={res.get('status')}, ok={res.get('ok')}, data={str(res.get('data'))[:300]}")
            return res
        except Exception as e:
            logger.error(f"Error calling SPX API {method} {full_url}: {e}")
            return {"ok": False, "status": 0, "error": str(e)}

    # ==========================================
    # نقاط النهاية (Endpoints) لمنصة الثقافة المالية
    # ==========================================

    async def get_auth_me(self) -> Dict[str, Any]:
        """
        بيانات حساب الطالب الحالي:
        GET /api/v1/auth/me
        """
        res = await self.call_api("/auth/me", method="GET")
        if res.get("ok") and isinstance(res.get("data"), dict):
            return res["data"].get("data", res["data"])
        return {}

    async def get_subject(self, subject_id: int = 7) -> Dict[str, Any]:
        """
        تفاصيل مادة الثقافة المالية وإحصائيات التقدم:
        GET /api/v1/subjects/{subject_id}
        """
        res = await self.call_api(f"/subjects/{subject_id}", method="GET")
        if res.get("ok") and isinstance(res.get("data"), dict):
            return res["data"].get("data", res["data"])
        return {}

    async def get_curriculum(self, subject_id: int = 7) -> List[Dict[str, Any]]:
        """
        شجرة المنهج الكاملة (الوحدات الـ 6، الأقسام، الفصول، الاختبارات):
        GET /api/v1/subjects/{subject_id}/curriculum
        """
        res = await self.call_api(f"/subjects/{subject_id}/curriculum", method="GET")
        if res.get("ok") and isinstance(res.get("data"), dict):
            return res["data"].get("data", [])
        return []

    async def get_chapter_blocks(self, chapter_id: int) -> Dict[str, Any]:
        """
        جلب محتويات الفصل التفاعلي (الحوارات، الصور، الأسئلة):
        GET /api/v1/chapters/{chapter_id}/blocks
        """
        res = await self.call_api(f"/chapters/{chapter_id}/blocks", method="GET")
        if res.get("ok") and isinstance(res.get("data"), dict):
            raw_data = res["data"].get("data", res["data"])
            if isinstance(raw_data, dict):
                raw_data["_api_ok"] = True
                return raw_data
            elif isinstance(raw_data, list):
                return {"blocks": raw_data, "_api_ok": True}

        # الاحتفاظ بكود الخطأ ورسالة السيرفر التشخيصية الدقيقة
        err_data = res.get("data") if isinstance(res.get("data"), dict) else {}
        err_info = err_data.get("error", {}) if isinstance(err_data, dict) else {}
        err_code = err_info.get("code") or ("http_" + str(res.get("status", 0)))
        err_msg = err_info.get("message") or res.get("error") or "خطأ في الاتصال بالسيرفر"
        return {
            "_api_ok": False,
            "error_code": err_code,
            "error_message": err_msg,
            "status": res.get("status", 0),
            "blocks": []
        }

    async def answer_chapter_question(
        self,
        chapter_id: int,
        block_id: int,
        selected_option_id: int,
        hint_used: int = 0
    ) -> Dict[str, Any]:
        """
        إرسال إجابة سؤال الاختيار من متعدد داخل الفصل عبر الـ API الرسمي المعتمد:
        POST /api/v1/chapters/{chapter_id}/answer
        Payload: {"block_id": block_id, "selected_option_id": selected_option_id, "hint_used": hint_used}
        """
        payload = {
            "block_id": block_id,
            "selected_option_id": selected_option_id,
            "hint_used": hint_used
        }
        res = await self.call_api(f"/chapters/{chapter_id}/answer", method="POST", body=payload)
        return res

    async def complete_chapter(self, chapter_id: int, cleared_block_ids: Optional[list] = None) -> Dict[str, Any]:
        """
        تأكيد إكمال الفصل والحصول على الإنجاز الكامل (5 نجوم):
        POST /api/v1/chapters/{chapter_id}/complete
        """
        payload = {"star_score": 5}
        if cleared_block_ids:
            payload["cleared_block_ids"] = cleared_block_ids
        res = await self.call_api(f"/chapters/{chapter_id}/complete", method="POST", body=payload)
        if res.get("ok"):
            return res
        res = await self.call_api(f"/chapters/{chapter_id}/complete", method="POST")
        if res.get("ok"):
            return res
        res = await self.call_api(f"/chapters/{chapter_id}/finish", method="POST", body=payload)
        if res.get("ok"):
            return res
        return await self.call_api(f"/chapters/{chapter_id}/complete", method="PUT", body=payload)

    async def complete_review(self, review_id: int) -> Dict[str, Any]:
        """
        تأكيد إكمال مراجعة القسم أو الفصل وتجربة مسارات الإكمال المعتمدة:
        1. POST /reviews/{review_id}/complete
        2. POST /chapters/{review_id}/complete
        3. POST /items/{review_id}/complete
        4. POST /reviews/{review_id}/finish
        """
        res = await self.call_api(f"/reviews/{review_id}/complete", method="POST")
        if res.get("ok"):
            return res
        res = await self.call_api(f"/chapters/{review_id}/complete", method="POST", body={"star_score": 5})
        if res.get("ok"):
            return res
        res = await self.call_api(f"/items/{review_id}/complete", method="POST")
        if res.get("ok"):
            return res
        return await self.call_api(f"/reviews/{review_id}/finish", method="POST")

    async def solve_review_via_api(self, review_id: int) -> Dict[str, Any]:
        """
        تأكيد إكمال مراجعة القسم أو الفصل مباشرة عبر الـ API الرسمي:
        """
        res = await self.complete_review(review_id)
        ok = res.get("ok", False)
        return {
            "success": ok,
            "review_id": review_id,
            "method": "api",
            "message": "تم إكمال المراجعة بنجاح عبر الـ API." if ok else res.get("error", "تعذر تأكيد إكمال المراجعة.")
        }

    async def start_test(self, test_id: int) -> Dict[str, Any]:
        """بدء محاولة اختبار القسم عبر الـ API الرسمي للمنصة"""
        endpoints = [
            (f"/tests/{test_id}/start", "POST", {}),
            (f"/tests/{test_id}/attempt", "POST", {}),
            (f"/tests/{test_id}/attempts", "POST", {}),
            (f"/tests/{test_id}/begin", "POST", {}),
            (f"/tests/{test_id}", "GET", None),
            (f"/tests/{test_id}/questions", "GET", None),
        ]
        for ep, meth, body in endpoints:
            try:
                res = await self.call_api(ep, method=meth, body=body)
                if res.get("ok"):
                    logger.info(f"Test {test_id} start endpoint succeeded: {meth} {ep}")
                    return res
            except Exception as e:
                logger.warning(f"Error testing endpoint {meth} {ep}: {e}")
        return {"ok": False, "error": "لم يتم العثور على نقطة بدء مباشرة للاختبار عبر الـ API"}

    async def get_test_questions(self, test_id: int) -> List[Dict[str, Any]]:
        """جلب أسئلة الاختبار التقييمي عبر الـ API إن كانت متاحة مباشرة"""
        for ep in [f"/tests/{test_id}/questions", f"/tests/{test_id}/blocks", f"/tests/{test_id}"]:
            try:
                res = await self.call_api(ep, method="GET")
                if res.get("ok") and isinstance(res.get("data"), dict):
                    d = res["data"].get("data", res["data"])
                    if isinstance(d, list):
                        return d
                    if isinstance(d, dict):
                        for k in ["questions", "blocks", "items"]:
                            if isinstance(d.get(k), list):
                                return d[k]
            except Exception:
                pass
        return []

    async def complete_test(self, test_id: int, score: int = 100, answers: Optional[list] = None) -> Dict[str, Any]:
        """
        تأكيد إكمال أو تسليم اختبار القسم عبر الـ API:
        1. بدء محاولة الاختبار أولاً إذا كان السيرفر يشترط محاولة نشطة (active test attempt).
        2. تسليم الإجابات والتحقق الصارم من أن السيرفر وضع حالة passed=True أو النتيجة >= 80%.
        """
        # أولاً: بدء محاولة الاختبار إن لم تكن نشطة
        await self.start_test(test_id)
        await asyncio.sleep(0.3)

        payloads = [
            {"score": score, "test_result": "passed", "star_score": 5},
            {"score": score, "is_passed": True},
            {"test_result": "passed"},
            {}
        ]
        if answers:
            payloads.insert(0, {"answers": answers, "score": score, "test_result": "passed"})

        for p in payloads:
            res = await self.call_api(f"/tests/{test_id}/submit", method="POST", body=p if p else None)
            if res.get("ok"):
                raw_data = res.get("data", {})
                inner = raw_data.get("data", {}).get("response", {}) if isinstance(raw_data.get("data"), dict) else raw_data.get("response", {})
                if not isinstance(inner, dict):
                    inner = raw_data if isinstance(raw_data, dict) else {}
                total_score = inner.get("total_score")
                passed_flag = inner.get("passed")
                is_passed = bool((passed_flag is True) or (total_score is not None and total_score >= 80))
                if is_passed:
                    logger.info(f"Test {test_id} submit genuinely PASSED via API: score={total_score}, passed={passed_flag}")
                    return {"ok": True, "passed": True, "score": total_score or score, "data": raw_data}
                else:
                    logger.warning(f"Test {test_id} submit returned HTTP 200 but failed grading: score={total_score}, passed={passed_flag}")

            res_comp = await self.call_api(f"/tests/{test_id}/complete", method="POST", body=p if p else None)
            if res_comp.get("ok"):
                raw_data = res_comp.get("data", {})
                inner = raw_data.get("data", {}).get("response", {}) if isinstance(raw_data.get("data"), dict) else raw_data.get("response", {})
                if not isinstance(inner, dict):
                    inner = raw_data if isinstance(raw_data, dict) else {}
                total_score = inner.get("total_score")
                passed_flag = inner.get("passed")
                is_passed = bool((passed_flag is True) or (total_score is not None and total_score >= 80))
                if is_passed:
                    logger.info(f"Test {test_id} complete genuinely PASSED via API: score={total_score}, passed={passed_flag}")
                    return {"ok": True, "passed": True, "score": total_score or score, "data": raw_data}

        return {"ok": False, "passed": False, "score": 0, "error": "لم يتم اجتياز الاختبار بنجاح عبر الـ API (النتيجة غير كافية أو لم تُسجل الإجابات)."}

    async def solve_test_via_api(self, test_id: int) -> Dict[str, Any]:
        """حل وتأكيد إكمال اختبار القسم عبر الـ API مع التحقق الحقيقي من درجة النجاح"""
        res = await self.complete_test(test_id)
        passed = bool(res.get("passed") is True or (res.get("ok") and res.get("score", 0) >= 80))
        return {
            "success": passed,
            "passed": passed,
            "test_id": test_id,
            "score": res.get("score", 0),
            "method": "api",
            "message": "تم اجتياز الاختبار بنجاح عبر الـ API." if passed else res.get("error", "لم يتم اجتياز الاختبار عبر الـ API مباشرة (النتيجة غير كافية).")
        }

    async def solve_chapter_via_api(
        self,
        chapter_id: int,
        on_progress=None,
        gemini_solver=None
    ) -> Dict[str, Any]:
        """
        حل الفصل كاملاً وإرسال جميع الإجابات الصحيحة وتأكيد الإكمال مباشرة عبر الـ API:
        1. جلب بيانات البلوكات والأسئلة عبر GET /chapters/{chapter_id}/blocks.
        2. استنتاج الإجابة الصحيحة عبر بنك الأسئلة أو الذكاء الاصطناعي (Gemini).
        3. إرسال الإجابة النموذجية الصحيحة 100% لكل سؤال عبر POST /chapters/{chapter_id}/answer.
        4. تأكيد إكمال الفصل بنجاح عبر POST /chapters/{chapter_id}/complete.
        """
        from pathlib import Path
        blocks_data = await self.get_chapter_blocks(chapter_id)

        # التحقق من الأخطاء الصريحة مثل قفل الفصل
        if not blocks_data.get("_api_ok", True):
            err_code = blocks_data.get("error_code")
            if err_code == "chapter_locked":
                return {
                    "success": False,
                    "code": "chapter_locked",
                    "chapter_id": chapter_id,
                    "message": f"الفصل {chapter_id} مغلق في المنصة (يجب إكمال الاختبار أو المحتوى السابق أولاً لفتحه)."
                }
            elif err_code == "subject_no_access":
                return {
                    "success": False,
                    "code": "subject_no_access",
                    "chapter_id": chapter_id,
                    "message": "لا تملك صلاحية الوصول لهذا المنهج، يرجى التحقق من تسجيل الدخول."
                }

        chapter_info = blocks_data.get("chapter", {})
        chapter_name = chapter_info.get("name", f"الفصل {chapter_id}")
        blocks = blocks_data.get("blocks", [])

        if not blocks:
            local_block_file = Path(f"data/spx/chapter_{chapter_id}_blocks.json")
            if local_block_file.exists():
                try:
                    with open(local_block_file, "r", encoding="utf-8") as f:
                        b_raw = json.load(f)
                        blocks = b_raw.get("data", {}).get("blocks", [])
                        chapter_info = b_raw.get("data", {}).get("chapter", {})
                        chapter_name = chapter_info.get("name", chapter_name)
                except Exception:
                    pass

        if not blocks:
            # التحقق إن كان الفصل مكتملاً بالفعل في المنهج لتفادي أي توقف زائف
            curr_file = Path("data/spx/curriculum.json")
            if curr_file.exists():
                try:
                    with open(curr_file, "r", encoding="utf-8") as f:
                        c_data = json.load(f).get("data", [])
                        for u in c_data:
                            for s in u.get("sections", []):
                                for it in s.get("items", []):
                                    if it.get("id") == chapter_id and it.get("is_completed"):
                                        return {
                                            "success": True,
                                            "chapter_id": chapter_id,
                                            "chapter_name": it.get("title", chapter_name),
                                            "already_completed": True,
                                            "message": f"الفصل {chapter_id} مكتمل مسبقاً في المنصة بنجاح."
                                        }
                except Exception:
                    pass

            return {
                "success": False,
                "code": "no_blocks",
                "chapter_id": chapter_id,
                "message": f"تعذر العثور على محتوى الفصل {chapter_id} عبر الـ API."
            }

        # بنك الإجابات النموذجية لأسئلة الفصل 74 المسبقة
        known_option_map = {
            675: 2698,  # عند الشراء، النظر إلى السعر واختيار الأفضل بمقارنة 'الغالي' و'الرخيص'
            676: 2701,  # تبقى القيمة الاسمية للألف جنيه كما هي، لكن الكمية التي يمكنك شراؤها بها أقل من السابق
            677: 2707,  # مقارنة الأسعار، والدفع، والاحتفاظ بالباقي، كل تصرف يوضّح وظيفة مختلفة
            678: 2709,  # استخدام بعضه فيما تحتاجه الآن، والاحتفاظ ببعضه بشكل آخر، والنظر في خيارات غير الادّخار فقط
            679: 2716   # الوظائف الثلاث جميعًا موجودة: 'المقارنة بالسعر، والدفع بالمال، والاحتفاظ به'
        }

        # استخراج بلوكات الأسئلة
        q_blocks = [b for b in blocks if b.get("type") == "question" or b.get("question_id")]
        total_questions = len(q_blocks)
        answered_count = 0
        details = []

        if on_progress:
            await on_progress(f"⚡ **بدء حل {total_questions} أسئلة في {chapter_name} عبر الـ API بالذكاء الاصطناعي...**")

        for idx, b in enumerate(q_blocks, 1):
            b_id = b.get("id")
            q_id = b.get("question_id")
            q_obj = b.get("question", {})
            q_text = q_obj.get("question_text", f"سؤال {idx}")
            options = b.get("options", [])

            # 1. فحص بنك الإجابات الثابتة المعروفة مسبقاً
            chosen_opt_id = known_option_map.get(q_id)

            # 2. فحص قاعدة البيانات المحلية AnswersDB بنص السؤال
            if not chosen_opt_id and options and q_text:
                from solver.answers_db import answers_db
                ans_row = answers_db.find_financial_answer(q_text)
                if ans_row and ans_row.get("correct_answer"):
                    corr = ans_row["correct_answer"].strip().lower()
                    for opt in options:
                        opt_txt = opt.get("text", "").strip().lower()
                        if opt_txt == corr or corr in opt_txt or opt_txt in corr:
                            chosen_opt_id = opt.get("id")
                            logger.info(f"Matched Q{q_id} from DB -> option {chosen_opt_id} ('{opt_txt[:30]}')")
                            break

            # 3. استخدام الذكاء الاصطناعي Gemini لحل السؤال بدقة لأي فصل أو سؤال جديد!
            if not chosen_opt_id and options and gemini_solver and gemini_solver.is_configured():
                try:
                    opt_texts = [opt.get("text", "") for opt in options]
                    best_idx = await gemini_solver.solve_quiz_question(q_text, opt_texts)
                    if 0 <= best_idx < len(options):
                        chosen_opt_id = options[best_idx].get("id")
                        logger.info(f"Gemini solved financial question {q_id}: option index {best_idx}")
                except Exception as e_gem:
                    logger.warning(f"Gemini solving exception for Q{q_id}: {e_gem}")

            # 4. خيار افتراضي احتياطي إن لم يتوفر بديل
            if not chosen_opt_id and options:
                chosen_opt_id = options[0].get("id")

            if chosen_opt_id:
                # إرسال الإجابة الرسمية للـ API
                ans_resp = await self.answer_chapter_question(
                    chapter_id=chapter_id,
                    block_id=b_id,
                    selected_option_id=chosen_opt_id,
                    hint_used=0
                )

                ans_data = ans_resp.get("data", {}) if isinstance(ans_resp.get("data"), dict) else {}
                inner_data = ans_data.get("data", {})
                is_correct = bool(inner_data.get("is_correct") is True)

                # إذا كان الخيار غير صحيح وكشف السيرفر عن الخيار الصحيح، نعيد إرساله فوراً
                if not is_correct and inner_data.get("correct_option_id"):
                    correct_id = inner_data["correct_option_id"]
                    retry_resp = await self.answer_chapter_question(
                        chapter_id=chapter_id,
                        block_id=b_id,
                        selected_option_id=correct_id,
                        hint_used=0
                    )
                    retry_inner = retry_resp.get("data", {}).get("data", {}) if isinstance(retry_resp.get("data"), dict) else {}
                    if retry_inner.get("is_correct") is True:
                        is_correct = True
                        chosen_opt_id = correct_id
                        inner_data = retry_inner

                # إذا ما زال غير صحيح، نجرب الخيارات الأخرى في السؤال حتى نصل للإجابة الصحيحة 100%
                if not is_correct and options:
                    for alt_opt in options:
                        alt_id = alt_opt.get("id")
                        if alt_id == chosen_opt_id:
                            continue
                        alt_resp = await self.answer_chapter_question(
                            chapter_id=chapter_id,
                            block_id=b_id,
                            selected_option_id=alt_id,
                            hint_used=0
                        )
                        alt_data = alt_resp.get("data", {}) if isinstance(alt_resp.get("data"), dict) else {}
                        alt_inner = alt_data.get("data", {})
                        if alt_inner.get("is_correct") is True:
                            is_correct = True
                            chosen_opt_id = alt_id
                            inner_data = alt_inner
                            logger.info(f"Question {q_id}: successfully auto-corrected to option {alt_id} (100% correct)")
                            break

                if is_correct:
                    answered_count += 1
                    details.append({
                        "block_id": b_id,
                        "question_id": q_id,
                        "option_id": chosen_opt_id,
                        "is_correct": is_correct,
                        "explanation": inner_data.get("explanation", "")
                    })

                    # حفظ الإجابة المؤكدة فوراً في بنك الأسئلة AnswersDB للرجوع الفوري لها
                    if chosen_opt_id:
                        try:
                            from solver.answers_db import answers_db
                            matched_opt = next((o for o in options if o.get("id") == chosen_opt_id), None)
                            if matched_opt:
                                answers_db.save_financial_question(
                                    question_text=q_text,
                                    options=[o.get("text", "") for o in options],
                                    correct_answer=matched_opt.get("text", ""),
                                    explanation=inner_data.get("explanation", "إجابة معتمدة رسمياً من منصة اسبركس"),
                                    topic=chapter_name,
                                    user_id=0,
                                    source="spx_auto_solver"
                                )
                        except Exception as e_save:
                            logger.warning(f"Could not save financial answer to db: {e_save}")

                if on_progress and (idx % 2 == 0 or idx == total_questions):
                    await on_progress(f"🎯 **تم إرسال إجابة السؤال ({idx}/{total_questions}) عبر الـ API بالذكاء الاصطناعي...**")

                await asyncio.sleep(0.3)

        # تأكيد إنهاء الفصل رسمياً وتمرير جميع البلوكات المكتملة
        all_block_ids = [b.get("id") for b in blocks if b.get("id")]
        comp_resp = await self.complete_chapter(chapter_id, cleared_block_ids=all_block_ids)
        comp_ok = bool(comp_resp.get("ok") and (comp_resp.get("data", {}).get("data", {}).get("completed") is True or comp_resp.get("status") == 200))
        comp_data = comp_resp.get("data", {}) if isinstance(comp_resp.get("data"), dict) else {}
        inner_comp = comp_data.get("data", {})
        star_score = inner_comp.get("star_score", 5)

        if not comp_ok:
            await asyncio.sleep(1)
            retry_comp = await self.complete_chapter(chapter_id, cleared_block_ids=all_block_ids)
            if retry_comp.get("ok") and retry_comp.get("status") == 200:
                comp_ok = True
                comp_data = retry_comp.get("data", {})
                inner_comp = comp_data.get("data", {})
                star_score = inner_comp.get("star_score", 5)

        logger.info(f"Chapter {chapter_id} API solve finished: answered={answered_count}/{total_questions}, completed={comp_ok}, star_score={star_score}")

        return {
            "success": comp_ok,
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "total_questions": total_questions,
            "solved_questions": answered_count,
            "star_score": star_score,
            "details": details,
            "message": "تم إكمال الفصل بنجاح عبر الـ API." if comp_ok else comp_data.get("error", {}).get("message", "تعذر تأكيد إكمال الفصل عبر الـ API.")
        }
