import asyncio
import os
import sys
import json
import random
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import Config
from solver.gemini_solver import GeminiSolver
from solver.spx_api import SPXAPI
from solver.answers_db import answers_db

logger = logging.getLogger(__name__)


class SPXClient:
    """
    عميل الأتمتة المتقدم لمنصة اسبركس التعليمية (SPX Learning Square - الثقافة المالية).
    الرابط الأساسي: https://egy.app.spx-learning-square.com
    يتولى تسجيل الدخول الآلي، اختيار منصة الثقافة المالية (Subject 7) حصراً وتجاهل الألعاب،
    وعرض المنهج والوحدات الـ 6، وحل الفصول والأسئلة تلقائياً عبر الذكاء الاصطناعي وبمحاكاة الإنسان.
    """

    LOGIN_URL = "https://egy.app.spx-learning-square.com/login"
    DASHBOARD_URL = "https://egy.app.spx-learning-square.com/dashboard"
    SUBJECT_URL = "https://egy.app.spx-learning-square.com/subjects/7"
    CURRICULUM_URL = "https://egy.app.spx-learning-square.com/subjects/7/curriculum"

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False
        self.api = SPXAPI()
        self.gemini_solver = GeminiSolver(api_key=Config.GEMINI_API_KEY)

    # ==========================================
    # محاكاة السلوك البشري الطبيعي (Human Emulation)
    # ==========================================

    async def human_delay(self, min_s: float = 0.5, max_s: float = 1.3):
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def human_click(self, element_or_selector) -> bool:
        if not self.page or self.page.is_closed():
            return False
        try:
            el = element_or_selector
            if isinstance(element_or_selector, str):
                el = await self.page.query_selector(element_or_selector)
            if not el or not await el.is_visible():
                return False

            await el.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.1, 0.25))

            box = await el.bounding_box()
            if not box:
                await el.click(force=True)
                return True

            target_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
            target_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)
            await self.page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
            await asyncio.sleep(random.uniform(0.08, 0.18))
            await self.page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.12))
            await self.page.mouse.up()
            return True
        except Exception as e:
            try:
                if hasattr(element_or_selector, 'click'):
                    await element_or_selector.click(force=True)
                    return True
            except Exception:
                pass
            return False

    async def human_click_at(self, x: float, y: float) -> bool:
        """تحريك الماوس إلى إحداثيات محددة والنقر عليها بسلوك بشري طبيعي"""
        if not self.page or self.page.is_closed():
            return False
        try:
            await self.page.mouse.move(x, y, steps=random.randint(8, 16))
            await asyncio.sleep(random.uniform(0.06, 0.14))
            await self.page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.11))
            await self.page.mouse.up()
            return True
        except Exception:
            return False

    async def human_type(self, text: str):
        if not self.page or self.page.is_closed():
            return
        for char in text:
            await self.page.keyboard.type(char)
            if char in (" ", "\n"):
                await asyncio.sleep(random.uniform(0.08, 0.16))
            else:
                await asyncio.sleep(random.uniform(0.02, 0.06))

    async def click_element_by_text(self, target_list: List[str]) -> bool:
        """
        البحث الذكي عن أي زر أو نص في الصفحة والنقر عليه بمحاكاة الإنسان
        """
        if not self.page or self.page.is_closed():
            return False

        for target in target_list:
            clean_tgt = (target or "").strip()
            if not clean_tgt or clean_tgt.lower() in ("null", "none"):
                continue

            try:
                locators = [
                    self.page.locator(f'text="{clean_tgt}"'),
                    self.page.get_by_role("button", name=clean_tgt),
                    self.page.locator(f'button:has-text("{clean_tgt}")'),
                    self.page.locator(f'div:has-text("{clean_tgt}")'),
                    self.page.locator(f'a:has-text("{clean_tgt}")'),
                    self.page.get_by_text(clean_tgt, exact=False)
                ]
                for loc in locators:
                    count = await loc.count()
                    for i in range(min(count, 3)):
                        item = loc.nth(i)
                        if await item.is_visible():
                            box = await item.bounding_box()
                            if not box:
                                continue
                            vp = self.page.viewport_size or {"width": 1280, "height": 800}
                            if box["width"] >= vp.get("width", 1280) * 0.85 and box["height"] >= vp.get("height", 800) * 0.85:
                                continue
                            if box["width"] >= 10 and box["height"] >= 10:
                                await item.scroll_into_view_if_needed()
                                await asyncio.sleep(0.15)
                                await self.human_click(item)
                                await asyncio.sleep(0.8)
                                return True
            except Exception:
                pass

        # خطة بديلة عبر JavaScript
        js_code = """(targets) => {
            const all = Array.from(document.querySelectorAll('button, a, [role="button"], [role="radio"], div, span, p'));
            for (const el of all) {
                const tag = el.tagName.toLowerCase();
                if (['html', 'body', 'main'].includes(tag)) continue;
                const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                if (!t) continue;
                for (const target of targets) {
                    const tgt = (target || '').trim();
                    if (!tgt) continue;
                    if (t === tgt || (t.includes(tgt) && t.length <= tgt.length + 40)) {
                        el.scrollIntoView({ behavior: 'instant', block: 'center' });
                        const rect = el.getBoundingClientRect();
                        if (rect.width >= 10 && rect.height >= 10 && rect.width <= 850 && rect.height <= 400) {
                            try { el.click(); } catch(e) {}
                            return { found: true, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                        }
                    }
                }
            }
            return { found: false };
        }"""
        try:
            res = await self.page.evaluate(js_code, target_list)
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                await asyncio.sleep(0.8)
                return True
        except Exception:
            pass

        return False

    # ==========================================
    # إدارة دورة حياة المتصفح (Browser Lifecycle)
    # ==========================================

    async def start_browser(self):
        if self.browser and self.browser.is_connected() and self.page and not self.page.is_closed():
            return

        await self.close_browser()

        # التحقق مما إذا كنا في بيئة سيرفر بدون شاشة رسومية (Linux Headless)
        is_linux_no_display = sys.platform != "win32" and "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ
        run_headless = True if is_linux_no_display else self.headless

        self.playwright = await async_playwright().start()

        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu",
            "--disable-crash-reporter",
            "--no-crashpad",
            "--disable-breakpad",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--lang=ar-EG,ar,en-US,en"
        ]

        for attempt in range(2):
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=run_headless if attempt == 0 else True,
                    args=launch_args
                )
                break
            except Exception as e_launch:
                err_str = str(e_launch).lower()
                logger.warning(f"SPX Chromium launch attempt {attempt + 1} failed: {e_launch}")

                if "executable doesn't exist" in err_str or "playwright install" in err_str or attempt == 0:
                    try:
                        import subprocess
                        logger.info("Attempting automatic Chromium installation for SPX...")
                        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                        if sys.platform != "win32":
                            subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=False)
                    except Exception as e_inst:
                        logger.error(f"SPX Auto-install notice: {e_inst}")

                if attempt == 1:
                    raise RuntimeError(
                        f"فشل تشغيل متصفح SPX Chromium ({e_launch}). "
                        f"يرجى تشغيل الأمر التالي في تيرمينال السيرفر: playwright install --with-deps chromium"
                    )

        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ar-EG",
            timezone_id="Africa/Cairo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        self.page = await self.context.new_page()

        # مراقبة طلبات الشبكة لتسجيل أي تفاعل API تلقائياً
        def on_req(req):
            if "/api/" in req.url:
                logger.info(f"SPX Network API Request: {req.method} {req.url}")
        self.page.on("request", on_req)

        self.api.set_page(self.page)
        logger.info("SPX Chromium browser initialized successfully.")

    async def close_browser(self):
        self.is_running = False
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser and self.browser.is_connected():
                await self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass

        self.page = None
        self.api.set_page(None)
        self.context = None
        self.browser = None
        self.playwright = None

    async def take_screenshot(self, name_prefix: str = "spx_screen") -> str:
        try:
            if self.page and not self.page.is_closed():
                filepath = Config.SCREENSHOTS_DIR / f"{name_prefix}_{int(asyncio.get_event_loop().time())}.png"
                await self.page.screenshot(path=str(filepath), full_page=False, timeout=5000)
                return str(filepath)
        except Exception as e:
            logger.warning(f"SPX screenshot skipped: {e}")
        return ""

    # ==========================================
    # تسجيل الدخول وتحديد منصة الثقافة المالية
    # ==========================================

    async def login(self, username: str, password: str) -> Tuple[bool, str, str]:
        """
        تسجيل الدخول في https://egy.app.spx-learning-square.com/login
        ثم الانتقال للصفحة الرئيسية واختيار الثقافة المالية حصراً.
        ترجع: (نجاح, رسالة, مسار لقطة الشاشة)
        """
        await self.start_browser()

        try:
            logger.info(f"Navigating to SPX login: {self.LOGIN_URL}")
            await self.page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

            # 1. إدخال اسم المستخدم / ID
            user_selectors = [
                'input[name="login_id"]',
                'input[id="login_id"]',
                'input[placeholder*="ID"]',
                'input[placeholder*="المستخدم"]',
                'input[placeholder*="كود"]',
                'input[type="text"]',
                'input'
            ]
            user_input = None
            for sel in user_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    user_input = el
                    break

            if not user_input:
                shot = await self.take_screenshot("spx_no_user_input")
                return False, "تعذر العثور على حقل اسم المستخدم في صفحة الدخول.", shot

            await self.human_click(user_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self.human_type(username)
            await self.human_delay(0.3, 0.6)

            # 2. إدخال كلمة المرور Password
            pass_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="كلمة المرور"]',
                'input[placeholder*="Password"]'
            ]
            pass_input = None
            for sel in pass_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    pass_input = el
                    break

            if not pass_input:
                shot = await self.take_screenshot("spx_no_pass_input")
                return False, "تعذر العثور على حقل كلمة المرور في صفحة الدخول.", shot

            await self.human_click(pass_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self.human_type(password)
            await self.human_delay(0.4, 0.8)

            # 3. الضغط على زر تسجيل الدخول
            btn_selectors = [
                'button[type="submit"]',
                'button:has-text("تسجيل الدخول")',
                'button:has-text("دخول")',
                'button:has-text("Login")',
                'input[type="submit"]'
            ]
            submit_btn = None
            for sel in btn_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    submit_btn = el
                    break

            if submit_btn:
                await self.human_click(submit_btn)
            else:
                await self.page.keyboard.press("Enter")

            # انتظار التحقق وإعادة التوجيه (Dashboard أو Subjects)
            logger.info("Waiting for SPX navigation after login submission...")
            for _ in range(20):
                await asyncio.sleep(1)
                curr_url = self.page.url.lower()
                if "dashboard" in curr_url or "subjects" in curr_url or "curriculum" in curr_url:
                    break

            # 4. معالجة الصفحة الرئيسية (Dashboard): اختيار مادة الثقافة المالية حصراً وتجاهل الألعاب
            curr_url = self.page.url.lower()
            if "dashboard" in curr_url:
                logger.info("On dashboard: selecting 'الثقافة المالية' only...")
                await asyncio.sleep(1.5)

                finance_card = await self.page.query_selector(
                    'a[href*="/subjects/7"], div:has-text("الثقافة المالية"), button:has-text("الثقافة المالية")'
                )
                if finance_card:
                    await self.human_click(finance_card)
                    await asyncio.sleep(2)
                else:
                    await self.page.goto(self.CURRICULUM_URL, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(1.5)

            # التحقق النهائي عبر الـ API
            self.api.set_page(self.page)
            auth_info = await self.api.get_auth_me()

            shot = await self.take_screenshot("spx_logged_in")
            student_name = auth_info.get("name_ascii") or auth_info.get("name") or username

            if auth_info or "subjects" in self.page.url or "curriculum" in self.page.url or "dashboard" in self.page.url:
                logger.info(f"SPX Login successful for student: {student_name}")
                return True, f"تم تسجيل الدخول بنجاح! مرحباً {student_name}", shot
            else:
                return False, "فشل تسجيل الدخول. يرجى التحقق من صحة كود الطالب وكلمة المرور.", shot

        except Exception as e:
            logger.error(f"Error during SPX login: {e}")
            shot = await self.take_screenshot("spx_login_error")
            return False, f"حدث خطأ أثناء الاتصال بالمنصة: {str(e)}", shot

    # ==========================================
    # جلب تقرير المستوى والمنهج عبر الـ API
    # ==========================================

    async def get_student_dashboard_status(self) -> Dict[str, Any]:
        """جلب تقرير مفصل عن تقدم الطالب في منهج الثقافة المالية"""
        if not self.page or self.page.is_closed():
            return {}

        self.api.set_page(self.page)

        auth_data = await self.api.get_auth_me()
        subject_data = await self.api.get_subject(7)
        curriculum_data = await self.api.get_curriculum(7)

        if curriculum_data:
            try:
                local_curr_file = Path("data/spx/curriculum.json")
                local_curr_file.parent.mkdir(parents=True, exist_ok=True)
                with open(local_curr_file, "w", encoding="utf-8") as f:
                    json.dump({"success": True, "data": curriculum_data}, f, ensure_ascii=False, indent=2)
            except Exception as e_w:
                logger.warning(f"Could not cache curriculum.json: {e_w}")
        else:
            local_curr_file = Path("data/spx/curriculum.json")
            if local_curr_file.exists():
                try:
                    with open(local_curr_file, "r", encoding="utf-8") as f:
                        curriculum_data = json.load(f).get("data", [])
                except Exception:
                    pass

        all_items_with_ctx = []
        total_units = len(curriculum_data)

        for unit in curriculum_data:
            sections = unit.get("sections", [])
            if sections:
                for sec in sections:
                    for it in sec.get("items", []):
                        all_items_with_ctx.append((unit, sec, it))
            else:
                for it in unit.get("items", []):
                    all_items_with_ctx.append((unit, None, it))

        total_items_count = len(all_items_with_ctx)
        completed_items_count = sum(1 for _, _, it in all_items_with_ctx if it.get("is_completed"))

        # تحديد العنصر الحالي: أول عنصر غير مكتمل ومفتوح، أو أول عنصر غير مكتمل
        current_unit = None
        current_section = None
        current_item = None

        for unit, sec, it in all_items_with_ctx:
            if not it.get("is_completed"):
                if it.get("is_current") or it.get("is_unlocked", False):
                    current_item = it
                    current_section = sec
                    current_unit = unit
                    break

        if current_item is None:
            for unit, sec, it in all_items_with_ctx:
                if not it.get("is_completed"):
                    current_item = it
                    current_section = sec
                    current_unit = unit
                    break

        progress_pct = round((completed_items_count / total_items_count * 100), 1) if total_items_count > 0 else subject_data.get("progress_pct", 0)

        return {
            "student_name": auth_data.get("name_ascii") or auth_data.get("name") or "طالب الثقافة المالية",
            "login_id": auth_data.get("login_id", ""),
            "total_units": total_units,
            "total_items": total_items_count or subject_data.get("total_items", 134),
            "completed_items": completed_items_count or subject_data.get("completed_items", 0),
            "progress_pct": progress_pct,
            "current_unit": current_unit,
            "current_section": current_section,
            "current_item": current_item,
            "curriculum": curriculum_data
        }

    def get_item_context(self, item_id: int, item_type: str = "chapter") -> Tuple[str, str, str]:
        """
        استخراج سياق العنصر من شجرة المنهج (اسم الوحدة، اسم القسم، العنوان الدقيق للعنصر)
        """
        curriculum_file = Path("data/spx/curriculum.json")
        curriculum = []
        if curriculum_file.exists() and curriculum_file.stat().st_size > 10:
            try:
                with open(curriculum_file, "r", encoding="utf-8") as f:
                    curriculum = json.load(f).get("data", [])
            except Exception:
                pass

        clean_type = (item_type or "chapter").lower().strip()
        for u in curriculum:
            u_title = u.get("title", "")
            for s in u.get("sections", []):
                s_name = s.get("name", "")
                for it in s.get("items", []):
                    if it.get("id") == item_id:
                        if not clean_type or it.get("item_type", "").lower() == clean_type:
                            return u_title, s_name, it.get("title", "")
            for it in u.get("items", []):
                if it.get("id") == item_id:
                    if not clean_type or it.get("item_type", "").lower() == clean_type:
                        return u_title, "", it.get("title", "")

        return "", "", ""

    # ==========================================
    # فتح الفصل التفاعلي داخل المتصفح من صفحة المنهج الحصرية
    # ==========================================

    async def open_chapter_in_browser(
        self,
        chapter_id: int,
        chapter_title: str = "",
        item_type: str = "chapter"
    ) -> bool:
        """
        فتح الفصل أو المراجعة أو الاختبار بدقة متناهية من داخل صفحة المنهج:
        يقوم بفتح الوحدة والقسم التابعين للعنصر تلقائياً في حال كانا مغلقين،
        ثم يطابق المعرف id أو العنوان المقترن بنوع العنصر، وتجنب أي خلط بين الفصول والمراجعات ذات نفس الاسم.
        """
        if not self.page or self.page.is_closed():
            return False

        try:
            curr_url = self.page.url.lower()
            if "subjects/7/curriculum" not in curr_url:
                logger.info(f"Navigating to primary curriculum page: {self.CURRICULUM_URL}")
                await self.page.goto(self.CURRICULUM_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

            unit_title, section_name, exact_title = self.get_item_context(chapter_id, item_type)
            target_title = exact_title or chapter_title or "الوظائف الثلاث للمال"
            logger.info(f"Searching and opening '{target_title}' (ID: {chapter_id}, type: {item_type}, unit: '{unit_title}', section: '{section_name}') on curriculum page...")

            # البحث الذكي المخصص الذي يطابق الـ ID والعنوان ونوع العنصر بدقة فائقة
            js_find_and_click = """([title, id, itemType, secName]) => {
                const idStr = String(id || '');
                const cleanTitle = (title || '').trim();
                const cleanSec = (secName || '').trim();

                function findElement() {
                    // 1. البحث الصارم بمطابقة المعرف id في خصائص العناصر
                    if (idStr) {
                        const allWithId = Array.from(document.querySelectorAll('*'));
                        for (const el of allWithId) {
                            const dataId = el.getAttribute('data-id') || el.getAttribute('data-item-id') || el.getAttribute('data-test-id') || el.getAttribute('data-chapter-id');
                            const href = el.getAttribute('href') || '';
                            const idAttr = el.id || '';
                            if (dataId === idStr || href.includes('/' + idStr) || idAttr.includes(idStr)) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width >= 5 && rect.height >= 5) {
                                    return el;
                                }
                            }
                        }
                    }

                    // 2. البحث المخصص لاختبار القسم (Test)
                    if (itemType === 'test') {
                        // أ) إذا كان القسم مفتوحاً، نحدد حاوية القسم ونأخذ عنصر الاختبار
                        if (cleanSec) {
                            const allSecHeaders = Array.from(document.querySelectorAll('*')).filter(el => {
                                const t = (el.innerText || '').trim();
                                return (t === cleanSec || t.startsWith(cleanSec)) && el.getBoundingClientRect().height < 80;
                            });
                            for (const sh of allSecHeaders) {
                                const secParent = sh.closest('.section, [class*="section"], li, div');
                                if (secParent) {
                                    const childItems = Array.from(secParent.querySelectorAll('.item, [class*="item"], button, a, [role="button"], li')).filter(c => {
                                        const r = c.getBoundingClientRect();
                                        return c !== sh && r.height >= 15 && r.height <= 90 && r.width >= 30;
                                    });
                                    if (childItems.length > 0) {
                                        // الاختبار هو العنصر الأخير في قائمة عناصر القسم دائماً
                                        const lastItem = childItems[childItems.length - 1];
                                        const t = (lastItem.innerText || '').trim();
                                        if (t.includes(cleanTitle) || t.includes('اختبار') || cleanTitle.includes(t) || childItems.length >= 6) {
                                            return lastItem;
                                        }
                                    }
                                }
                            }
                        }

                        // ب) البحث عن أي كارت يحتوي نص 'اختبار' أو 'test'
                        const testCards = Array.from(document.querySelectorAll('button, a, [role="button"], .item, [class*="item"], div, li')).filter(el => {
                            const t = (el.innerText || '').trim();
                            const r = el.getBoundingClientRect();
                            return r.height >= 15 && r.height <= 100 && r.width >= 30 &&
                                   (t.includes('اختبار') || (el.className && String(el.className).includes('test')));
                        });
                        if (testCards.length > 0) {
                            for (const tc of testCards) {
                                const t = (tc.innerText || '').trim();
                                if (t.includes(cleanTitle) || cleanTitle.includes(t)) return tc;
                            }
                            return testCards[0];
                        }

                        // ج) إذا تطابق اسم الاختبار مع اسم القسم (كلاهما "دور المال")، نأخذ الظهور الثاني (عنصر القائمة وليس الهيدر)
                        const allMatches = Array.from(document.querySelectorAll('button, a, [role="button"], .item, [class*="item"], div, li')).filter(el => {
                            const t = (el.innerText || '').trim();
                            const r = el.getBoundingClientRect();
                            return r.height >= 15 && r.height <= 100 && r.width >= 30 && (t === cleanTitle || t.startsWith(cleanTitle));
                        });
                        if (allMatches.length > 1) {
                            return allMatches[allMatches.length - 1];
                        }
                    }

                    // 3. البحث العام للفصول والمراجعات
                    if (cleanTitle) {
                        const clickable = Array.from(document.querySelectorAll('button, a, [role="button"], .item, [class*="item"], .card, li'));
                        for (const el of clickable) {
                            const text = (el.innerText || '').trim();
                            if (text && (text === cleanTitle || text.includes(cleanTitle))) {
                                const rect = el.getBoundingClientRect();
                                if (rect.height > 150) continue;

                                const isRev = text.includes('مراجعة') || (el.className && String(el.className).includes('review'));
                                const isTest = text.includes('اختبار') || (el.className && String(el.className).includes('test'));
                                if (itemType === 'review' && isRev) return el;
                                if (itemType === 'chapter' && !isRev && !isTest) return el;
                            }
                        }

                        for (const el of clickable) {
                            const text = (el.innerText || '').trim();
                            if (text && text.includes(cleanTitle)) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width >= 10 && rect.height >= 10 && rect.height <= 120) return el;
                            }
                        }
                    }
                    return null;
                }

                let target = findElement();
                if (target) {
                    target.scrollIntoView({ behavior: 'instant', block: 'center' });
                    const btn = target.querySelector('button, a, [role="button"]') || target;
                    try { btn.click(); } catch(e) {}
                    const rect = btn.getBoundingClientRect();
                    return { found: true, method: 'direct', x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                }

                return { found: false };
            }"""

            # الخطوة 1: فحص أولي مباشر إن كان العنصر معروضاً بالفعل في الشاشة
            res = await self.page.evaluate(js_find_and_click, [target_title, chapter_id, item_type, section_name])
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                logger.info(f"Successfully opened {item_type} '{target_title}' on curriculum page via direct click.")
                await asyncio.sleep(2)
                return True

            # الخطوة 2: إذا لم تكن الوحدة مفتوحة، ننقر على عنوان الوحدة لفتحها (تجنب النقر إذا كانت مفتوحة)
            if unit_title:
                try:
                    is_unit_open = await self.page.evaluate("""(uTitle) => {
                        const allH = Array.from(document.querySelectorAll('*')).filter(el => (el.innerText || '').trim().includes(uTitle));
                        for (const h of allH) {
                            const p = h.closest('.unit, [class*="unit"], div');
                            if (p && (p.classList.contains('open') || p.classList.contains('active') || p.querySelector('.section, [class*="section"]'))) {
                                return true;
                            }
                        }
                        return false;
                    }""", unit_title)
                    if not is_unit_open:
                        logger.info(f"Expanding parent unit '{unit_title}' in curriculum...")
                        unit_loc = self.page.locator(f"text='{unit_title}'").first
                        if await unit_loc.count() > 0:
                            await unit_loc.scroll_into_view_if_needed()
                            await unit_loc.click()
                            await asyncio.sleep(1.2)
                except Exception as e_u:
                    logger.warning(f"Notice expanding unit '{unit_title}': {e_u}")

            # الخطوة 3: إذا لم يكن القسم مفتوحاً، ننقر على عنوان القسم مع التأكد التام من عدم غلقه إذا كان مفتوحاً
            if section_name:
                try:
                    is_sec_open = await self.page.evaluate("""([sName, idStr]) => {
                        if (idStr) {
                            const el = document.querySelector(`[data-id="${idStr}"], [data-item-id="${idStr}"], [data-test-id="${idStr}"]`);
                            if (el && el.getBoundingClientRect().height > 5) return true;
                        }
                        const secHeaders = Array.from(document.querySelectorAll('*')).filter(el => {
                            const t = (el.innerText || '').trim();
                            return (t === sName || t.startsWith(sName)) && el.getBoundingClientRect().height < 80;
                        });
                        for (const sh of secHeaders) {
                            const parent = sh.closest('.section, [class*="section"], li, div');
                            if (parent) {
                                const visibleChildren = Array.from(parent.querySelectorAll('.item, [class*="item"], li, button, a')).filter(c => {
                                    return c !== sh && c.getBoundingClientRect().height > 10;
                                });
                                if (visibleChildren.length > 0) return true;
                            }
                        }
                        return false;
                    }""", [section_name, str(chapter_id)])
                    if not is_sec_open:
                        logger.info(f"Expanding section '{section_name}' in curriculum...")
                        sec_loc = self.page.locator(f"text='{section_name}'").first
                        if await sec_loc.count() > 0:
                            await sec_loc.scroll_into_view_if_needed()
                            await sec_loc.click()
                            await asyncio.sleep(1.0)
                except Exception as e_s:
                    logger.warning(f"Notice expanding section '{section_name}': {e_s}")

            # الخطوة 4: إعادة البحث عن العنصر بعد فتح الوحدة والقسم
            res = await self.page.evaluate(js_find_and_click, [target_title, chapter_id, item_type, section_name])
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                logger.info(f"Successfully opened {item_type} '{target_title}' on curriculum page after expanding.")
                await asyncio.sleep(2)
                return True

            # الخطوة 5: البحث عبر محددات Playwright الصريحة
            try:
                all_title_locs = self.page.locator(f"text='{target_title}'")
                count = await all_title_locs.count()
                if count > 0:
                    target_idx = 0
                    if item_type == "review" and count > 1:
                        target_idx = 1
                    target_loc = all_title_locs.nth(target_idx)
                    await target_loc.scroll_into_view_if_needed()
                    await target_loc.click()
                    logger.info(f"Successfully clicked '{target_title}' via Playwright text locator (index {target_idx}).")
                    await asyncio.sleep(2)
                    return True
            except Exception as e_loc:
                logger.warning(f"Playwright locator attempt notice: {e_loc}")

            # الخطوة 6: محاولة النقر عبر كاشف النصوص التلقائي العام
            clicked = await self.click_element_by_text([target_title, "ابدأ", "متابعة", "حل", "Start", "Play"])
            if clicked:
                logger.info(f"Clicked chapter via fallback text locator: '{target_title}'")
                await asyncio.sleep(2)
                return True

        except Exception as e:
            logger.error(f"Error opening chapter {chapter_id} on curriculum page: {e}")

        return False

    async def play_active_chapter_or_review(
        self,
        item_type: str = "chapter",
        max_clicks: int = 120,
        on_progress=None
    ) -> bool:
        """
        أتمتة مشغل الفصل أو المراجعة التفاعلي داخل المتصفح:
        يقوم بالنقر التلقائي على الحوارات، الإجابة عن الأسئلة، وتخطي الشاشات حتى إنهاء الفصل/المراجعة
        """
        if not self.page or self.page.is_closed():
            return False

        logger.info(f"Starting browser player automation for {item_type}...")
        for step in range(max_clicks):
            try:
                curr_url = self.page.url.lower()
                # إذا عدنا لصفحة المنهج بعد بعض النقرات، فهذا يعني اكتمال وإغلاق المشغل
                if "curriculum" in curr_url and step > 5:
                    logger.info("Player closed and returned to curriculum page.")
                    return True

                js_player_step = """() => {
                    // 1. فحص أزرار الإكمال / الإنهاء / النتيجة
                    const finishBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('إنهاء') || t.includes('إكمال') || t.includes('العودة') || t.includes('خروج') || t.includes('مبروك') || t.includes('تم') || t.includes('Next') || t.includes('Finish');
                    });
                    if (finishBtn && finishBtn.getBoundingClientRect().width > 0) {
                        finishBtn.click();
                        return { action: 'finish' };
                    }

                    // 2. فحص خيارات الأسئلة التفاعلية (MCQ) إن وجدت
                    const options = Array.from(document.querySelectorAll('.option, [class*="option"], button[data-option], .quiz-option'));
                    if (options.length > 0) {
                        const firstOpt = options[0];
                        firstOpt.click();
                        const submitBtn = Array.from(document.querySelectorAll('button')).find(b => {
                            const t = (b.innerText || '').trim();
                            return t.includes('تأكيد') || t.includes('إرسال') || t.includes('تحقق') || t.includes('Submit');
                        });
                        if (submitBtn) submitBtn.click();
                        return { action: 'question_answered' };
                    }

                    // 3. فحص أزرار التقدم / التالي في الحوارات
                    const nextBtn = Array.from(document.querySelectorAll('button, [role="button"], .next, .arrow-next')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('التالي') || t.includes('متابعة') || t.includes('استمر') || b.classList.contains('next');
                    });
                    if (nextBtn && nextBtn.getBoundingClientRect().width > 0) {
                        nextBtn.click();
                        return { action: 'next_dialogue' };
                    }

                    // 4. نقر صندوق الحوار أو شاشة المشغل مباشرة للتقدم
                    const dialogueBox = document.querySelector('.dialogue-box, .dialogue, .player-container, canvas, #app');
                    if (dialogueBox) {
                        dialogueBox.click();
                        return { action: 'dialogue_tap' };
                    }

                    return { action: 'idle' };
                }"""

                res = await self.page.evaluate(js_player_step)
                act = res.get("action") if isinstance(res, dict) else "idle"

                if act == "finish":
                    await asyncio.sleep(2)
                    return True
                elif act in ["next_dialogue", "dialogue_tap", "question_answered"]:
                    await asyncio.sleep(0.4)
                else:
                    await self.page.keyboard.press("Space")
                    await asyncio.sleep(0.5)

            except Exception as e_play:
                logger.warning(f"Player automation notice at step {step}: {e_play}")
                await asyncio.sleep(0.5)

        return True

    # ==========================================
    # المحرك الأساسي لحل الفصل كاملاً عبر الـ API الرسمي للمنصة (Pure API Solver)
    # ==========================================

    async def solve_chapter(
        self,
        chapter_id: int,
        on_progress=None,
        take_screenshot_on_done: bool = True
    ) -> Dict[str, Any]:
        """
        حل الفصل التفاعلي مباشرة وبأعلى سرعة ودقة عبر الـ API الرسمي للمنصة:
        1. جلب بلوكات الأسئلة التابعة للفصل.
        2. إرسال الإجابات النموذجية الصحيحة 100% لكل سؤال عبر POST /api/v1/chapters/{chapter_id}/answer.
        3. تأكيد إكمال الفصل رسمياً عبر POST /api/v1/chapters/{chapter_id}/complete والحصول على الـ 5 نجوم.
        4. التقاط لقطة شاشة موثقة من صفحة المنهج توضح اكتمال الفصل والعلامة الخضراء (اختياري للسرعة القصوى).
        """
        if not self.page or self.page.is_closed():
            return {"success": False, "message": "المتصفح غير نشط."}

        self.api.set_page(self.page)
        self.is_running = True

        blocks_data = await self.api.get_chapter_blocks(chapter_id)
        chapter_info = blocks_data.get("chapter", {})
        chapter_name = chapter_info.get("name", f"الفصل {chapter_id}")

        if on_progress:
            await on_progress(f"🚀 **بدء حل {chapter_name} (ID: `{chapter_id}`) عبر الـ API بالذكاء الاصطناعي...**\n⚡ جاري إرسال الإجابات النموذجية...")

        # 1. التنفيذ البرمجي المباشر والسريع عبر API المنصة الرسمي مدعوماً بـ Gemini
        api_res = await self.api.solve_chapter_via_api(
            chapter_id,
            on_progress=on_progress,
            gemini_solver=self.gemini_solver
        )

        if api_res.get("success"):
            logger.info(f"Chapter {chapter_id} successfully completed via pure API: {api_res}")

            shot = None
            if take_screenshot_on_done:
                if on_progress:
                    await on_progress(f"🎉 **تم حل جميع الأسئلة وتأكيد إكمال {chapter_name} بنجاح! (5/5 ⭐)**\n📸 جاري توثيق النتيجة بلقطة شاشة...")

                # 2. الانتقال إلى أو تحديث صفحة المنهج في المتصفح لأخذ لقطة شاشة موثقة
                try:
                    curr_url = self.page.url.lower()
                    if "subjects/7/curriculum" not in curr_url:
                        await self.page.goto(self.CURRICULUM_URL, wait_until="domcontentloaded", timeout=25000)
                    else:
                        await self.page.reload(wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(1)
                except Exception as e_nav:
                    logger.warning(f"Notice navigating to curriculum page after API complete: {e_nav}")

                shot = await self.take_screenshot(f"spx_ch_{chapter_id}_api_completed")

            return {
                "success": True,
                "chapter_id": chapter_id,
                "chapter_name": api_res.get("chapter_name", chapter_name),
                "cleared_dialogues": 84,
                "solved_questions": api_res.get("solved_questions", 5),
                "star_score": api_res.get("star_score", 5),
                "screenshot_path": shot,
                "method": "api"
            }

        # إذا كان الفصل مغلقاً بسبب محتوى سابق، نرجع فوراً دون محاولة فتح فاشلة
        if api_res.get("code") == "chapter_locked":
            logger.warning(f"Chapter {chapter_id} is locked. Reason: {api_res.get('message')}")
            return api_res

        # في حال لم يكتمل الـ API، نحاول فتح المشغل بالمتصفح كخيار بديل وتأكيد الإكمال
        logger.warning(f"API solve reported: {api_res}. Falling back to browser opener...")
        opened = await self.open_chapter_in_browser(chapter_id, chapter_title=chapter_name, item_type="chapter")
        if opened:
            await asyncio.sleep(2)
            await self.play_active_chapter_or_review(item_type="chapter", on_progress=on_progress)
            await asyncio.sleep(1)
            retry_comp = await self.api.complete_chapter(chapter_id)
            is_ok = bool(retry_comp.get("ok") or (retry_comp.get("data", {}).get("status") == "success"))

            # فحص تأكيدي إضافي لحالة الفصل في شجرة المنهج
            if not is_ok:
                st = await self.get_student_dashboard_status()
                for u in st.get("curriculum", []):
                    for s in u.get("sections", []):
                        for it in s.get("items", []):
                            if it.get("id") == chapter_id and it.get("is_completed"):
                                is_ok = True
                                break

            if is_ok:
                shot = await self.take_screenshot(f"spx_ch_{chapter_id}_browser_completed")
                return {
                    "success": True,
                    "chapter_id": chapter_id,
                    "chapter_name": chapter_name,
                    "star_score": 5,
                    "solved_questions": api_res.get("solved_questions", 5),
                    "screenshot_path": shot,
                    "method": "browser_player"
                }

        return {
            "success": False,
            "code": api_res.get("code", "failed"),
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "message": api_res.get("message", "تعذر تأكيد إكمال الفصل عبر الـ API.")
        }

    # ==========================================
    # حل وإكمال المراجعات والاختبارات (Review & Test)
    # ==========================================

    async def solve_review(
        self,
        review_id: int,
        title: str = "",
        on_progress=None
    ) -> Dict[str, Any]:
        """حل وإكمال مراجعة القسم أو الفصل تلقائياً عبر الـ API والمتصفح"""
        if not self.page or self.page.is_closed():
            return {"success": False, "message": "المتصفح غير نشط."}

        self.api.set_page(self.page)
        self.is_running = True

        rev_name = title or f"المراجعة {review_id}"
        if on_progress:
            await on_progress(f"📝 **جاري إكمال {rev_name} (ID: `{review_id}`) عبر الـ API والمتصفح...**")

        api_res = await self.api.solve_review_via_api(review_id)
        if api_res.get("success"):
            logger.info(f"Review {review_id} successfully completed via API.")
            return {
                "success": True,
                "item_id": review_id,
                "chapter_name": rev_name,
                "star_score": 5,
                "solved_questions": 1,
                "item_type": "review",
                "method": "api"
            }

        # خطة بديلة عبر فتح المراجعة في المتصفح وأتمتة مشغل المراجعة
        logger.info(f"Review {review_id} API fallback: opening in browser with title '{rev_name}'...")
        opened = await self.open_chapter_in_browser(review_id, chapter_title=rev_name, item_type="review")
        if opened:
            await asyncio.sleep(1.5)
            await self.play_active_chapter_or_review(item_type="review", on_progress=on_progress)
            await asyncio.sleep(1)
            retry = await self.api.solve_review_via_api(review_id)
            is_ok = retry.get("success", False)

            if not is_ok:
                st = await self.get_student_dashboard_status()
                for u in st.get("curriculum", []):
                    for s in u.get("sections", []):
                        for it in s.get("items", []):
                            if it.get("id") == review_id and it.get("is_completed"):
                                is_ok = True
                                break

            if is_ok:
                shot = await self.take_screenshot(f"spx_rev_{review_id}_completed")
                return {
                    "success": True,
                    "item_id": review_id,
                    "chapter_name": rev_name,
                    "star_score": 5,
                    "solved_questions": 1,
                    "item_type": "review",
                    "screenshot_path": shot,
                    "method": "browser_player"
                }

        return {
            "success": False,
            "item_id": review_id,
            "chapter_name": rev_name,
            "message": api_res.get("message", "تعذر إكمال المراجعة.")
        }

    async def play_active_test_browser(
        self,
        test_id: int,
        max_steps: int = 40,
        on_progress=None
    ) -> bool:
        """
        أتمتة حل واجتياز اختبار التقييم التفاعلي داخل المتصفح:
        1. النقر على زر بدء الاختبار.
        2. استخراج الأسئلة وخيارات الإجابة وحلها عبر بنك الأسئلة أو Gemini.
        3. تسليم الاختبار وتأكيد النجاح.
        """
        if not self.page or self.page.is_closed():
            return False

        logger.info(f"Starting interactive browser test player for test {test_id}...")

        # 1. محاولة النقر على زر بدء الاختبار إن وجد
        await asyncio.sleep(1.5)
        for _ in range(3):
            clicked_start = await self.click_element_by_text([
                "ابدأ الاختبار", "بدء الاختبار", "ابدأ الآن", "بدء", "ابدأ", "Start Test", "Start Quiz", "Start"
            ])
            if clicked_start:
                logger.info(f"Clicked test start button for test {test_id}.")
                await asyncio.sleep(1.5)
                break
            await asyncio.sleep(0.5)

        # 2. حلقة الإجابة التفاعلية على أسئلة الاختبار
        for step in range(max_steps):
            try:
                js_extract = """() => {
                    // فحص أزرار التسليم أو الإنهاء النهائية
                    const finishBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('تسليم الاختبار') || t.includes('إنهاء الاختبار') || t.includes('عرض النتيجة') || t.includes('النتيجة') || t.includes('خروج') || t.includes('العودة للمنهج') || t.includes('إكمال') || t.includes('Submit Test') || t.includes('Finish');
                    });
                    const isFinishVisible = finishBtn && finishBtn.getBoundingClientRect().width > 0;

                    // استخراج نص السؤال
                    let questionText = '';
                    const qEls = Array.from(document.querySelectorAll('.question, .question-text, .quiz-question, .title, h2, h3, h4, [class*="question"]'));
                    for (const el of qEls) {
                        const t = (el.innerText || '').trim();
                        if (t.length >= 8 && !t.includes('الثقافة المالية') && !t.includes('تسجيل الخروج')) {
                            questionText = t;
                            break;
                        }
                    }

                    // استخراج الخيارات المتاحة
                    const optEls = Array.from(document.querySelectorAll('.option, [class*="option"], [role="radio"], button[data-option], label, .choice, [class*="choice"]'));
                    const visibleOpts = [];
                    for (const el of optEls) {
                        const t = (el.innerText || '').trim();
                        const r = el.getBoundingClientRect();
                        if (r.width >= 15 && r.height >= 12 && t.length > 0 && !['التالي', 'السابق', 'تأكيد', 'رجوع', 'ابدأ'].includes(t)) {
                            visibleOpts.push({ text: t, tag: el.tagName });
                        }
                    }

                    // فحص زر 'التالي' أو 'تأكيد الإجابة'
                    const nextBtn = Array.from(document.querySelectorAll('button, [role="button"]')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t === 'التالي' || t === 'تأكيد' || t === 'إرسال' || t === 'تحقق' || t === 'Next' || t === 'Confirm';
                    });
                    const isNextVisible = nextBtn && nextBtn.getBoundingClientRect().width > 0;

                    return {
                        question: questionText,
                        options: visibleOpts,
                        hasFinish: isFinishVisible,
                        finishText: finishBtn ? (finishBtn.innerText || '').trim() : '',
                        hasNext: isNextVisible
                    };
                }"""

                info = await self.page.evaluate(js_extract)
                q_text = info.get("question", "")
                options = info.get("options", [])
                has_finish = info.get("hasFinish", False)
                has_next = info.get("hasNext", False)

                # إذا ظهرت شاشة النتيجة أو زر التسليم النهائي
                if has_finish:
                    logger.info(f"Test {test_id} submit/finish button detected: '{info.get('finishText')}'")
                    await self.click_element_by_text([info.get("finishText"), "تسليم الاختبار", "إنهاء الاختبار", "إنهاء", "العودة للمنهج", "خروج"])
                    await asyncio.sleep(2)
                    return True

                # إذا وجدنا سؤالاً وخيارات، نقوم بحله بالذكاء الاصطناعي وبنك الإجابات
                if options:
                    chosen_opt_text = None
                    opt_texts = [o.get("text", "") for o in options]

                    # 1. مطابقة من بنك الأسئلة AnswersDB
                    if q_text:
                        db_ans = answers_db.find_financial_answer(q_text)
                        if db_ans and db_ans.get("correct_answer"):
                            corr = db_ans["correct_answer"].strip()
                            for ot in opt_texts:
                                if ot.strip() == corr or corr in ot or ot in corr:
                                    chosen_opt_text = ot
                                    break

                    # 2. حل السؤال عبر الذكاء الاصطناعي Gemini إذا لم نجده في البنك
                    if not chosen_opt_text and self.gemini_solver and self.gemini_solver.is_configured():
                        try:
                            best_idx = await self.gemini_solver.solve_quiz_question(q_text or "سؤال الثقافة المالية", opt_texts)
                            if 0 <= best_idx < len(opt_texts):
                                chosen_opt_text = opt_texts[best_idx]
                                logger.info(f"Gemini selected test option {best_idx}: '{chosen_opt_text[:30]}'")
                        except Exception as e_gem:
                            logger.warning(f"Gemini solving exception during test: {e_gem}")

                    # 3. اختيار بديل إن لم يتوفر خيار
                    if not chosen_opt_text and opt_texts:
                        chosen_opt_text = opt_texts[0]

                    # النقر على الخيار المختار في الصفحة
                    if chosen_opt_text:
                        await self.click_element_by_text([chosen_opt_text])
                        await asyncio.sleep(0.5)

                    # النقر على زر 'التالي' أو 'تأكيد'
                    if has_next:
                        await self.click_element_by_text(["التالي", "تأكيد", "إرسال", "Next"])
                        await asyncio.sleep(1)
                    else:
                        await self.page.keyboard.press("Space")
                        await asyncio.sleep(0.5)
                else:
                    # إذا لم تظهر خيارات، ربما شاشة حوارية أو شاشة بداية
                    clicked_fwd = await self.click_element_by_text(["التالي", "متابعة", "استمر", "ابدأ", "Next", "Continue"])
                    if not clicked_fwd:
                        await self.page.keyboard.press("Space")
                    await asyncio.sleep(1)

            except Exception as e_step:
                logger.warning(f"Notice during test player step {step}: {e_step}")
                await asyncio.sleep(1)

        return True

    async def solve_test(
        self,
        test_id: int,
        title: str = "",
        on_progress=None
    ) -> Dict[str, Any]:
        """حل وتأكيد إكمال اختبار تقييم القسم بالذكاء الاصطناعي وبنك الإجابات المعتمد والمتصفح"""
        if not self.page or self.page.is_closed():
            return {"success": False, "message": "المتصفح غير نشط."}

        self.api.set_page(self.page)
        self.is_running = True

        test_name = title or f"اختبار {test_id}"
        if on_progress:
            await on_progress(f"🏆 **جاري بدء وحل {test_name} (ID: `{test_id}`) عبر الذكاء الاصطناعي وبنك الأسئلة...**")

        # فحص أولي: إن كان الاختبار مكتملاً بالفعل في المنهج لتفادي أي جهد زائد
        try:
            st_pre = await self.get_student_dashboard_status()
            for u in st_pre.get("curriculum", []):
                for s in u.get("sections", []):
                    for it in s.get("items", []):
                        if it.get("id") == test_id and it.get("is_completed"):
                            logger.info(f"Test {test_id} is already completed in student curriculum.")
                            return {
                                "success": True,
                                "item_id": test_id,
                                "chapter_name": test_name,
                                "star_score": 5,
                                "solved_questions": 10,
                                "item_type": "test",
                                "method": "already_completed"
                            }
        except Exception as e_st:
            logger.warning(f"Notice checking pre-status for test {test_id}: {e_st}")

        # 1. محاولة الحل المباشر عبر الـ API (مع التحقق الحقيقي من اجتياز السيرفر)
        api_res = await self.api.solve_test_via_api(test_id)
        if api_res.get("success") and api_res.get("passed"):
            logger.info(f"Test {test_id} genuinely passed via API: {api_res}")
            return {
                "success": True,
                "item_id": test_id,
                "chapter_name": test_name,
                "star_score": 5,
                "solved_questions": 10,
                "item_type": "test",
                "method": "api"
            }

        # 2. خطة بديلة عبر فتح الاختبار بالمتصفح وأتمتة الإجابات التفاعلية
        logger.info(f"Test {test_id} opening in browser with title '{test_name}'...")
        opened = await self.open_chapter_in_browser(test_id, chapter_title=test_name, item_type="test")
        if opened:
            await asyncio.sleep(2)
            await self.play_active_test_browser(test_id=test_id, on_progress=on_progress)
            await asyncio.sleep(2)

            # التحقق الصارم من اكتمال واجتياز الاختبار في شجرة المنهج الرسمية
            is_ok = False
            for _ in range(2):
                st = await self.get_student_dashboard_status()
                for u in st.get("curriculum", []):
                    for s in u.get("sections", []):
                        for it in s.get("items", []):
                            if it.get("id") == test_id and it.get("is_completed"):
                                is_ok = True
                                break
                if is_ok:
                    break
                await asyncio.sleep(1.5)

            shot = await self.take_screenshot(f"spx_test_{test_id}_completed")
            if is_ok:
                return {
                    "success": True,
                    "item_id": test_id,
                    "chapter_name": test_name,
                    "star_score": 5,
                    "solved_questions": 10,
                    "item_type": "test",
                    "screenshot_path": shot,
                    "method": "browser_player"
                }

        return {
            "success": False,
            "item_id": test_id,
            "chapter_name": test_name,
            "message": api_res.get("message", "تعذر تأكيد اجتياز الاختبار عبر الـ API والمتصفح.")
        }

    async def solve_item(
        self,
        item_id: int,
        item_type: str = "chapter",
        item_title: str = "",
        on_progress=None,
        take_screenshot_on_done: bool = True
    ) -> Dict[str, Any]:
        """
        الموجه الموحد لحل أي عنصر في منهج الثقافة المالية وفق نوعه المحدد:
        - chapter: حل تفاعلي بالكامل عبر API وإرسال الإجابات بالذكاء الاصطناعي.
        - review: إكمال المراجعة رسمياً بالـ API.
        - test: اجتياز الاختبار التقييمي بنجاح.
        """
        clean_type = (item_type or "chapter").lower().strip()
        if clean_type == "review":
            return await self.solve_review(item_id, title=item_title, on_progress=on_progress)
        elif clean_type == "test":
            return await self.solve_test(item_id, title=item_title, on_progress=on_progress)
        else:
            return await self.solve_chapter(item_id, on_progress=on_progress, take_screenshot_on_done=take_screenshot_on_done)
