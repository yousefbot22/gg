import asyncio
import os
import sys
import random
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import Config
from solver.gemini_solver import GeminiSolver
from solver.qureo_api import QureoAPI


class QureoClient:
    """عميل الأتمتة للتعامل مع منصة كيريو التعليمية باستخدام Playwright بمحاكاة سلوك الإنسان"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False
        self.active_course_url = Config.DEFAULT_COURSE_URL
        self.api = QureoAPI()

    # ==========================================
    # محاكاة سلوك الإنسان الحقيقي (Human Emulation)
    # ==========================================

    async def human_delay(self, min_s: float = 0.5, max_s: float = 1.4):
        """فترة انتظار عشوائية واقعية تحاكي تفكير الطالب وقراءة الشاشة"""
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def human_scroll(self, direction: str = "down", steps: int = 3):
        """محاكاة التمرير بعجلة الماوس بشكل سلس وتدريجي كالإنسان"""
        if not self.page or self.page.is_closed():
            return
        try:
            delta = 160 if direction == "down" else -160
            for _ in range(steps):
                await self.page.mouse.wheel(delta_x=0, delta_y=delta + random.randint(-25, 25))
                await asyncio.sleep(random.uniform(0.08, 0.16))
        except Exception:
            pass

    async def human_click(self, element_or_selector) -> bool:
        """تحريك مؤشر الماوس بمسار طبيعي والضغط على العنصر مثل الإنسان تماماً"""
        if not self.page or self.page.is_closed():
            return False

        try:
            el = element_or_selector
            if isinstance(element_or_selector, str):
                el = await self.page.query_selector(element_or_selector)

            if not el or not await el.is_visible():
                return False

            # التمرير السلس حتى يظهر العنصر في الشاشة
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.12, 0.28))

            box = await el.bounding_box()
            if not box:
                await el.click(force=True)
                return True

            # فحص أمان صارم: إذا كان العنصر يغطي معظم الشاشة كـ body أو html، نرفض النقر عليه فوراً
            vp = self.page.viewport_size or {"width": 1280, "height": 800}
            if box["width"] >= vp.get("width", 1280) * 0.75 and box["height"] >= vp.get("height", 800) * 0.75:
                print(f"Safety warning: Ignored click on full-screen container ({box['width']}x{box['height']})")
                return False

            # نقطة عشوائية طبيعية داخل مساحة الزر
            target_x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
            target_y = box["y"] + box["height"] * random.uniform(0.35, 0.65)

            # تحريك الماوس بمسار بشري متعدد الخطوات
            await self.page.mouse.move(target_x, target_y, steps=random.randint(12, 22))
            await asyncio.sleep(random.uniform(0.08, 0.2))

            # النقر الفعلي (Mouse Down ثم Mouse Up) بزمن واقعي
            await self.page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.11))
            await self.page.mouse.up()
            return True

        except Exception:
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
            # إضافة إزاحة طفيفة طبيعية (+- 3px)
            real_x = x + random.uniform(-3, 3)
            real_y = y + random.uniform(-3, 3)
            await self.page.mouse.move(real_x, real_y, steps=random.randint(10, 20))
            await asyncio.sleep(random.uniform(0.06, 0.15))
            await self.page.mouse.down()
            await asyncio.sleep(random.uniform(0.05, 0.12))
            await self.page.mouse.up()
            return True
        except Exception as e:
            print(f"Error in human_click_at: {e}")
            return False

    async def click_element_by_text(self, targets: Any) -> bool:
        """
        البحث الذكي والنقر الدقيق على أي زر أو عنصر يحتوي على أي من النصوص المحددة،
        مع إعطاء الأولوية لمحددات Playwright الأصلية لضمان تفاعل المتصفح وحركة الماوس
        """
        if not self.page or self.page.is_closed():
            return False

        if isinstance(targets, str):
            target_list = [targets]
        else:
            target_list = list(targets)

        # 1. تجربة محددات Playwright الحقيقية أولاً (Native Locators & Pointer Events)
        for tgt in target_list:
            clean_tgt = str(tgt).strip()
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
                    for i in range(min(count, 4)):
                        item = loc.nth(i)
                        if await item.is_visible():
                            box = await item.bounding_box()
                            if not box:
                                continue

                            # تجنب الحاويات الكاملة للشاشة
                            vp = self.page.viewport_size or {"width": 1280, "height": 800}
                            if box["width"] >= vp.get("width", 1280) * 0.75 and box["height"] >= vp.get("height", 800) * 0.75:
                                continue

                            if box["width"] >= 15 and box["height"] >= 15:
                                print(f"Clicking via Playwright locator: '{clean_tgt}' at ({box['x']}, {box['y']})")
                                await item.scroll_into_view_if_needed()
                                await asyncio.sleep(0.2)
                                await self.human_click(item)
                                await asyncio.sleep(2)
                                return True
            except Exception as e_loc:
                print(f"Notice Playwright locator for '{clean_tgt}': {e_loc}")

        # 2. خطة بديلة متقدمة عبر JavaScript (إيجاد البطاقة وحساب الإحداثيات بعد التمرير الفوري)
        js_code = """(targets) => {
            function findCard(doc) {
                if (!doc) return null;
                const all = Array.from(doc.querySelectorAll('button, a, [role="button"], div, span, p, input[type="button"], input[type="submit"]'));
                for (const el of all) {
                    const tag = el.tagName.toLowerCase();
                    if (['html', 'body', 'main', 'header', 'footer'].includes(tag)) continue;
                    if (el.id === 'root' || el.id === '__next' || el.id === 'app') continue;

                    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                    if (!t) continue;

                    for (const target of targets) {
                        const tgt = (target || '').trim();
                        if (!tgt) continue;
                        if (t.includes("المحرر الحر") && !tgt.includes("المحرر")) continue;

                        if (t === tgt || (t.includes(tgt) && t.length <= tgt.length + 35)) {
                            // التمرير الفوري دون أنيميشن drift
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            const finalRect = el.getBoundingClientRect();
                            if (finalRect.width >= 15 && finalRect.height >= 15 && finalRect.width <= 750 && finalRect.height <= 350) {
                                try { el.click(); } catch(e) {}
                                if (el.parentElement) {
                                    try { el.parentElement.click(); } catch(e) {}
                                }
                                return {
                                    found: true,
                                    x: finalRect.left + finalRect.width / 2,
                                    y: finalRect.top + finalRect.height / 2
                                };
                            }
                        }
                    }
                }
                const iframes = doc.querySelectorAll('iframe');
                for (const iframe of iframes) {
                    try {
                        const r = findCard(iframe.contentDocument || iframe.contentWindow.document);
                        if (r) return r;
                    } catch(e) {}
                }
                return null;
            }

            const res = findCard(document);
            return res || { found: false };
        }"""

        try:
            res = await self.page.evaluate(js_code, target_list)
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                await asyncio.sleep(2)
                return True
        except Exception as e:
            print(f"Notice in click_element_by_text JS: {e}")

        return False

    async def human_type(self, text: str):
        """كتابة النصوص بحركات مفاتيح بشرية وسرعات متغيرة طبيعية بين الأحرف"""
        if not self.page or self.page.is_closed():
            return

        if len(text) > 150:
            await asyncio.sleep(random.uniform(0.4, 0.9))
            await self.page.keyboard.insert_text(text)
            return

        for char in text:
            await self.page.keyboard.type(char)
            if char in (" ", "\n", "\t"):
                await asyncio.sleep(random.uniform(0.08, 0.18))
            elif char in (".", ",", ":", ";", "=", "+", "-", "_", "(", ")"):
                await asyncio.sleep(random.uniform(0.06, 0.14))
            else:
                await asyncio.sleep(random.uniform(0.025, 0.065))

    async def start_browser(self):
        """تشغيل جلسة المتصفح والتأكد من أنها متصلة ونشطة مع توافق كامل لبيئات السيرفرات"""
        # إذا كان المتصفح أو الصفحة مغلقة، نعيد تهيئتها بالكامل
        if self.browser is not None:
            try:
                if not self.browser.is_connected() or self.page is None or self.page.is_closed():
                    await self.close_browser()
            except Exception:
                await self.close_browser()

        if self.browser is None:
            # التحقق مما إذا كنا في بيئة سيرفر بدون شاشة رسومية (Linux Headless)
            is_linux_no_display = sys.platform != "win32" and "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ
            run_headless = True if is_linux_no_display else self.headless

            print(f"Launching Playwright Chromium (headless={run_headless})...")
            self.playwright = await async_playwright().start()

            # حزمة أعلام كروميوم المتوافقة 100% مع بيئات السيرفرات والحاويات لمنع تعطل Crashpad والخطأ 22
            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-crash-reporter",
                "--no-crashpad",
                "--disable-breakpad",
                "--no-first-run",
                "--no-zygote",
                "--disable-software-rasterizer",
                "--disable-extensions",
            ]
            if not run_headless:
                launch_args.append("--start-maximized")

            # محاولة التشغيل مع معالجة ذكية للأخطاء والتثبيت التلقائي لكروميوم إن كان مفقوداً
            for attempt in range(2):
                try:
                    self.browser = await self.playwright.chromium.launch(
                        headless=run_headless if attempt == 0 else True,
                        args=launch_args
                    )
                    break
                except Exception as e_launch:
                    err_str = str(e_launch).lower()
                    print(f"Notice: Chromium launch attempt {attempt + 1} failed: {e_launch}")

                    # إذا كان الخطأ بسبب نقص كروميوم أو اعتماداته، نحاول تثبيتها تلقائياً
                    if "executable doesn't exist" in err_str or "playwright install" in err_str or attempt == 0:
                        try:
                            import subprocess
                            print("Attempting automatic Chromium installation on server...")
                            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                            if sys.platform != "win32":
                                subprocess.run([sys.executable, "-m", "playwright", "install-deps", "chromium"], check=False)
                        except Exception as e_inst:
                            print(f"Auto-install notice: {e_inst}")

                    if attempt == 1:
                        raise RuntimeError(
                            f"فشل تشغيل متصفح Chromium ({e_launch}). "
                            f"يرجى تشغيل الأمر التالي في تيرمينال السيرفر: playwright install --with-deps chromium"
                        )

            try:
                self.context = await self.browser.new_context(
                    no_viewport=True if not run_headless else False,
                    viewport={"width": 1280, "height": 800} if run_headless else None,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            except Exception:
                self.context = await self.browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )

            self.page = await self.context.new_page()
            self.api.set_page(self.page)
            print("Chromium browser instance created successfully.")

    async def close_browser(self):
        """إغلاق المتصفح وتنظيف الجلسة بأمان"""
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

    async def take_screenshot(self, name_prefix: str = "screen") -> str:
        """أخذ لقطة شاشة وحفظها في مجلد لقطات الشاشة بأمان تام"""
        try:
            # إذا كانت الصفحة الحالية أغلقت أو غير موجودة، نبحث عن أي صفحة نشطة أخرى
            if self.page is None or self.page.is_closed():
                if self.context and len(self.context.pages) > 0:
                    for p in reversed(self.context.pages):
                        if not p.is_closed():
                            self.page = p
                            self.api.set_page(self.page)
                            break

            if self.page and not self.page.is_closed():
                filepath = Config.SCREENSHOTS_DIR / f"{name_prefix}_{int(asyncio.get_event_loop().time())}.png"
                await self.page.screenshot(path=str(filepath), full_page=False, timeout=5000)
                return str(filepath)
        except Exception as e:
            print(f"Notice: screenshot skipped ({e})")
        return ""

    async def login(self, username: str, password: str) -> Tuple[bool, str, str]:
        """
        تسجيل الدخول في منصة كيريو
        ترجع: (نجاح أو فشل, رسالة توضيحية, مسار لقطة الشاشة)
        """
        await self.start_browser()

        try:
            print(f"Navigating to login URL: {Config.LOGIN_URL}")
            await self.page.goto(Config.LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2)

            # ------------------------------------------------------------------
            # خطوة 0: فحص إذا كانت الصفحة تطلب الاختيار (بوابة اسبركس أو انتقل إلى تسجيل الدخول للتعلم)
            # "Go to Learning Login / انتقل إلى تسجيل الدخول للتعلم"
            # ------------------------------------------------------------------
            try:
                print("Checking for 'Go to Learning Login' option on landing page...")
                try:
                    await self.page.wait_for_selector(
                        'text="Learning Login", text="Go to Learning Login", text="التعلم", input',
                        timeout=10000
                    )
                except Exception:
                    pass

                clicked_learning = await self.click_element_by_text([
                    "Go to Learning Login",
                    "انتقل إلى تسجيل الدخول للتعلم",
                    "تسجيل الدخول للتعلم",
                    "Learning Login"
                ])

                # إذا لم يتم النقر بالنص، استهداف الزر الثاني مباشرة في الصفحة
                if not clicked_learning:
                    try:
                        buttons = await self.page.query_selector_all('button, a')
                        visible_btns = []
                        for b in buttons:
                            if await b.is_visible():
                                txt = (await b.text_content() or "").strip()
                                if "Sprix" in txt or "Learning" in txt or "سبريكس" in txt or "التعلم" in txt:
                                    visible_btns.append(b)
                        if len(visible_btns) >= 2:
                            print("Found both portal buttons, clicking the 2nd one (Learning Login)...")
                            await self.human_click(visible_btns[1])
                            clicked_learning = True
                    except Exception as e_btn:
                        print(f"Notice: 2nd button check info: {e_btn}")

                await asyncio.sleep(2)

                # فحص إذا تم فتح تبويب/نافذة جديدة
                if len(self.context.pages) > 1:
                    print(f"Detected new tab ({len(self.context.pages)} pages open). Switching to new tab...")
                    self.page = self.context.pages[-1]
                    self.api.set_page(self.page)
                    await self.page.bring_to_front()
                    await self.page.wait_for_load_state("domcontentloaded")

                # 5. انتظار ذكي حتى ظهور خانات اسم المستخدم وكلمة المرور
                print("Waiting for username and password fields to become visible...")
                for wait_step in range(12):
                    if len(self.context.pages) > 1:
                        self.page = self.context.pages[-1]
                        self.api.set_page(self.page)

                    u_check = await self.page.query_selector('input[type="text"], input[name="username"], input[name="id"], input[placeholder*="ID"], input')
                    p_check = await self.page.query_selector('input[type="password"]')
                    if u_check and p_check and await u_check.is_visible() and await p_check.is_visible():
                        print(f"Input fields detected and ready after {wait_step + 1}s!")
                        break
                    await asyncio.sleep(1)

            except Exception as e_nav:
                print(f"Notice during landing selection: {e_nav}")

            # ------------------------------------------------------------------
            # خطوة 1: محاولة إيجاد حقل اسم المستخدم
            # ------------------------------------------------------------------
            username_selectors = [
                'input[type="text"]',
                'input[name="username"]',
                'input[name="id"]',
                'input[placeholder*="اسم المستخدم"]',
                'input[placeholder*="ID"]',
                'input[placeholder*="الكود"]',
                'input'
            ]

            username_input = None
            for sel in username_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    username_input = el
                    break

            if not username_input:
                screenshot = await self.take_screenshot("login_failed_no_user_input")
                return False, "لم يتم العثور على حقل إدخال اسم المستخدم في الصفحة.", screenshot

            # كتابة اسم المستخدم بمحاكاة بشرية واقعية
            await self.human_click(username_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self.human_type(username)
            await self.human_delay(0.3, 0.7)

            # إيجاد حقل كلمة المرور
            password_input = await self.page.query_selector('input[type="password"]')
            if not password_input:
                screenshot = await self.take_screenshot("login_failed_no_pass_input")
                return False, "لم يتم العثور على حقل كلمة المرور في الصفحة.", screenshot

            # كتابة كلمة المرور بمحاكاة بشرية واقعية
            await self.human_click(password_input)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await self.human_type(password)
            await self.human_delay(0.4, 0.9)

            # النقر على زر تسجيل الدخول بتحريك الماوس الطبيعي
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("تسجيل الدخول")',
                'button:has-text("Login")',
                'button:has-text("دخول")',
                'input[type="submit"]',
                'button'
            ]

            submit_btn = None
            for sel in submit_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    submit_btn = el
                    break

            if submit_btn:
                await self.human_click(submit_btn)
            else:
                # محاولة الضغط على Enter
                await password_input.press("Enter")

            # انتظار التحميل والتوجيه
            await asyncio.sleep(4)
            current_url = self.page.url

            screenshot = await self.take_screenshot("after_login")

            # التحقق إذا ما زلنا في صفحة login أو ظهر خطأ
            if "login" in current_url:
                # التحقق من وجود رسالة خطأ
                error_el = await self.page.query_selector('.error, [role="alert"], .alert, .notification')
                err_text = await error_el.text_content() if error_el else "اسم المستخدم أو كلمة المرور غير صحيحة، أو يلزم التحقق."
                return False, f"فشل تسجيل الدخول: {err_text.strip()}", screenshot

            return True, "تم تسجيل الدخول بنجاح إلى منصة كيريو! 🎉", screenshot

        except Exception as e:
            screenshot = await self.take_screenshot("login_exception") if self.page else ""
            return False, f"حدث خطأ أثناء تسجيل الدخول: {str(e)}", screenshot

    async def close_free_editor_if_open(self) -> bool:
        """إغلاق نافذة المحرر الحر المنبثقة إذا فُتحت بالخطأ"""
        if not self.page or self.page.is_closed():
            return False
        try:
            closed = await self.page.evaluate("""() => {
                if (document.body.innerText.includes("المحرر الحر")) {
                    const elements = Array.from(document.querySelectorAll('button, div, span, svg, a'));
                    for (const el of elements) {
                        const rect = el.getBoundingClientRect();
                        // الزر الدائري للإغلاق في أعلى يسار النافذة
                        if (rect.left < 120 && rect.top < 80 && rect.width >= 15 && rect.height >= 15 && rect.width < 100 && rect.height < 100) {
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if closed:
                print("Closed 'المحرر الحر' modal successfully.")
                await asyncio.sleep(1.5)
                return True
        except Exception as e:
            print(f"Notice close_free_editor: {e}")
        return False

    async def click_start_or_resume(self) -> bool:
        """البحث عن زر 'ابدأ' أو 'بدء التعلم' أو متابعة والنقر عليه فوراً لبدء التمرين أو المستوى"""
        # أولاً نتأكد أن نافذة المحرر الحر ليست مفتوحة
        await self.close_free_editor_if_open()

        targets = [
            "بدء التعلم",
            "ابدأ",
            "Start",
            "متابعة",
            "استئناف"
        ]
        return await self.click_element_by_text(targets)

    async def select_course_card(self, course_name: str = "python") -> bool:
        """اختيار بطاقة الكورس من الصفحة الرئيسية بعد تسجيل الدخول (Python أو JavaScript)"""
        if "python" in str(course_name).lower():
            targets = ["Python", "بايثون"]
        else:
            targets = ["JavaScript", "جافاسكريبت", "JS"]
        return await self.click_element_by_text(targets)

    async def click_active_lesson_card(self) -> bool:
        """النقر على الدرس النشط أو التالي في قائمة الفصول للدخول للتمرين"""
        if not self.page or self.page.is_closed():
            return False

        # 1. أولاً: تجربة محددات Playwright الحقيقية للدروس الظاهرة في الشاشة
        lesson_keywords = [
            "التدرب على المتغيرات",
            "إسناد القيم إلى المتغيرات",
            "مراجعة",
            "التدرب",
            "التدريب"
        ]
        for kw in lesson_keywords:
            try:
                loc = self.page.locator(f'div:has-text("{kw}")')
                count = await loc.count()
                for i in range(min(count, 4)):
                    item = loc.nth(i)
                    if await item.is_visible():
                        box = await item.bounding_box()
                        if box and 120 <= box["width"] <= 550 and 30 <= box["height"] <= 130 and box["x"] < 800:
                            print(f"Found active lesson card via Playwright: '{kw}' at ({box['x']}, {box['y']})")
                            await item.scroll_into_view_if_needed()
                            await asyncio.sleep(0.2)
                            await self.human_click(item)
                            await asyncio.sleep(2.5)
                            return True
            except Exception:
                continue

        # 2. ثانياً: فحص ذكي عبر JavaScript للتعرف على البطاقات وتحديد غير المكتمل منها
        try:
            res = await self.page.evaluate("""() => {
                const all = Array.from(document.querySelectorAll('div, a, button, li'));
                const cards = [];
                const maxLeft = window.innerWidth * 0.70;

                for (const el of all) {
                    const tag = el.tagName.toLowerCase();
                    if (['html', 'body', 'main', 'header'].includes(tag)) continue;
                    if (el.id === 'root' || el.id === 'app') continue;

                    const rect = el.getBoundingClientRect();
                    // بطاقات الدروس في اللوحة اليسرى
                    if (rect.left < maxLeft && rect.width >= 120 && rect.width <= 520 && rect.height >= 30 && rect.height <= 120) {
                        const text = (el.innerText || "").trim();
                        if (!text || text.includes("سنتعلم") || text.includes("قائمة الفصول") || text.length > 70) continue;

                        const isLocked = el.querySelector('[class*="lock"]') !== null || text.includes('مقفل') || text.includes('🔒');
                        if (isLocked) continue;

                        const hasCheck = el.querySelector('svg, i, [class*="check"], [class*="done"]') !== null || text.includes('✓') || text.includes('✔');

                        cards.push({
                            el: el,
                            text: text,
                            completed: hasCheck,
                            area: rect.width * rect.height
                        });
                    }
                }

                if (cards.length > 0) {
                    const leafCards = cards.filter(c1 => !cards.some(c2 => c1 !== c2 && c1.el.contains(c2.el)));
                    const targetList = leafCards.length > 0 ? leafCards : cards;

                    // إعطاء الأولوية للدرس غير المكتمل
                    const uncompleted = targetList.filter(c => !c.completed);
                    const target = uncompleted.length > 0 ? uncompleted[0] : targetList[0];

                    target.el.scrollIntoView({ behavior: 'instant', block: 'center' });
                    const finalRect = target.el.getBoundingClientRect();
                    try { target.el.click(); } catch(e) {}
                    if (target.el.parentElement) {
                        try { target.el.parentElement.click(); } catch(e) {}
                    }

                    return {
                        found: true,
                        x: finalRect.left + finalRect.width / 2,
                        y: finalRect.top + finalRect.height / 2,
                        text: target.text
                    };
                }

                // فحص الفصول في اللوحة اليمنى
                const rightCards = [];
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width >= 120 && rect.width <= 320 && rect.height >= 35 && rect.height <= 100 && rect.left >= maxLeft) {
                        const text = (el.innerText || "").trim();
                        if (!text || text.includes("قائمة الفصول") || text.length > 40) continue;

                        const isLocked = el.querySelector('[class*="lock"]') !== null || text.includes('مقفل') || text.includes('🔒');
                        if (!isLocked) {
                            rightCards.push({ el: el, text: text });
                        }
                    }
                }

                if (rightCards.length > 0) {
                    const ch = rightCards[0];
                    ch.el.scrollIntoView({ behavior: 'instant', block: 'center' });
                    const finalRect = ch.el.getBoundingClientRect();
                    try { ch.el.click(); } catch(e) {}
                    return {
                        found: true,
                        x: finalRect.left + finalRect.width / 2,
                        y: finalRect.top + finalRect.height / 2,
                        text: ch.text
                    };
                }

                return { found: false };
            }""")

            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                print(f"Clicked lesson card successfully: {res.get('text', '')}")
                await asyncio.sleep(2.5)
                return True
        except Exception as e:
            print(f"Notice click_active_lesson_card: {e}")
        return False

    async def open_course(self, course_url: Optional[str] = None) -> Tuple[bool, str, str]:
        """فتح رابط المسار المحدد في المنصة والنقر على 'ابدأ' تلقائياً دون إعادة تحميل إذا كان مفتوحاً بالفعل"""
        target_url = course_url or self.active_course_url
        self.active_course_url = target_url

        try:
            current_url = self.page.url if (self.page and not self.page.is_closed()) else ""

            # إذا كان المتصفح موجوداً بالفعل داخل صفحة المسار أو أحد دروسه
            if current_url and target_url in current_url:
                print(f"Browser is already at course page: {current_url}")
                await self.click_start_or_resume()
                return True, "المسار مفتوح وجاهز للحل.", ""

            print(f"Navigating to course: {target_url}")
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)

            # إذا كنا في صفحة اختيار الكورسات، نضغط على بطاقة الكورس
            course_type = "python" if "python" in target_url.lower() else "javascript"
            await self.select_course_card(course_type)
            await asyncio.sleep(1.5)

            # النقر التلقائي على 'ابدأ' أو 'بدء التعلم'
            await self.click_start_or_resume()

            return True, "تم فتح صفحة المسار وبدء المستوى بنجاح.", ""
        except Exception as e:
            try:
                await self.page.goto(target_url, timeout=30000)
                await asyncio.sleep(2)
                await self.click_start_or_resume()
                return True, "تم فتح صفحة المسار بنجاح.", ""
            except Exception as e2:
                return False, f"فشل فتح المسار: {str(e2)}", ""

    async def solve_current_step(self, gemini_solver: GeminiSolver) -> Dict[str, Any]:
        """
        فحص الشاشة الحالية وحل التمرين أو السؤال باستخدام Gemini
        """
        if not self.page:
            return {"success": False, "message": "المتصفح غير نشط."}

        # التأكد من إغلاق نافذة المحرر الحر إذا كانت مفتوحة
        await self.close_free_editor_if_open()

        # 0. فحص إذا كان هناك زر 'ابدأ' أو 'بدء التعلم' في الشاشة
        if await self.click_start_or_resume():
            await asyncio.sleep(2)

        # 1. استخراج أي نصوص أو تعليمات من الصفحة
        page_text = await self.page.evaluate("""() => {
            return document.body.innerText || "";
        }""")

        # فحص مباشر إذا كان المستوى قد اكتمل
        if any(kw in page_text for kw in ["أحسنت", "تهانينا", "اكتمل المستوى", "المستوى التالي", "التالي بعد الحل"]):
            completion_screenshot = await self.take_screenshot("level_completed")
            await self.click_next_or_finish()
            await asyncio.sleep(2.5)
            await self.click_start_or_resume()
            return {
                "success": True,
                "type": "completed",
                "is_level_completed": True,
                "summary": "🎉 أحسنت! تم إكمال المستوى بنجاح.",
                "screenshot": completion_screenshot
            }

        # 2. التقاط لقطة شاشة للتحليل
        screenshot_path = await self.take_screenshot("step_attempt")

        # 3. محاولة استخراج كود المحرر الحالي إن وجد
        current_editor_code = await self.get_editor_code()

        # 4. تحليل الحالة بواسطة Gemini
        analysis = await gemini_solver.analyze_screen_and_guide(
            screenshot_path=screenshot_path,
            additional_context=page_text[:1500]
        )

        # تنظيف لقطة الشاشة المؤقتة فور الانتهاء من التحليل للحفاظ على المساحة
        if screenshot_path and Path(screenshot_path).exists():
            try:
                Path(screenshot_path).unlink(missing_ok=True)
            except Exception:
                pass

        page_type = analysis.get("page_type", "unknown")
        summary = analysis.get("summary", "")

        # فحص إذا أفاد Gemini أن المستوى اكتمل
        if page_type == "completed" or analysis.get("is_passed"):
            completion_screenshot = await self.take_screenshot("level_completed")
            await self.click_next_or_finish()
            await asyncio.sleep(2.5)
            await self.click_start_or_resume()
            return {
                "success": True,
                "type": "completed",
                "is_level_completed": True,
                "summary": "🎉 تم إكمال المستوى بنجاح!",
                "screenshot": completion_screenshot
            }

        # أ. إذا كانت الشاشة لوحة تحكم dashboard أو تطلب البدء
        if page_type == "dashboard" or "بدء التعلم" in page_text or "ابدأ" in page_text:
            if await self.click_start_or_resume():
                return {
                    "success": True,
                    "type": "start",
                    "is_level_completed": False,
                    "summary": "تم النقر على زر ابدأ / بدء التعلم.",
                    "screenshot": ""
                }

        # ب. إذا اقترح الذكاء الاصطناعي زراً محدداً بالاسم
        suggested_btn = analysis.get("next_button")
        if suggested_btn and str(suggested_btn).lower() not in ("null", "none", ""):
            print(f"Gemini suggested clicking: {suggested_btn}")
            clicked_sug = await self.click_element_by_text(suggested_btn)
            if clicked_sug:
                await asyncio.sleep(2.5)
                return {
                    "success": True,
                    "type": "general",
                    "is_level_completed": False,
                    "summary": f"تم النقر على: {suggested_btn}",
                    "screenshot": ""
                }

        # ج. إذا كانت الشاشة خريطة الفصول والدروس (chapter_map) أو ظهرت قائمة الفصول
        if page_type == "chapter_map" or "قائمة الفصول" in page_text:
            print("Detected chapter/lessons view, searching for active lesson...")
            if await self.click_active_lesson_card():
                await asyncio.sleep(3)
                return {
                    "success": True,
                    "type": "chapter_map",
                    "is_level_completed": False,
                    "summary": "تم فتح الدرس المتاح من قائمة الفصول.",
                    "screenshot": ""
                }

        # د. إذا كانت نافذة حوار أو تعليمات الروبوت (dialogue)
        if page_type == "dialogue":
            await self.click_next_or_finish()
            await asyncio.sleep(2)
            return {
                "success": True,
                "type": "dialogue",
                "is_level_completed": False,
                "summary": "تم متابعة الحوار التعليمي.",
                "screenshot": ""
            }

        # ج. إذا كانت شاشة تمرين برمجي (Code Task)
        if page_type == "code_task" or current_editor_code is not None:
            solution_code = analysis.get("solution_code")
            if not solution_code:
                # طلب الكود مباشرة من Gemini
                solution_code = await gemini_solver.solve_code_task(
                    instruction=summary or page_text[:800],
                    current_code=current_editor_code or "",
                    language="python" if "python" in self.active_course_url else "javascript",
                    screenshot_path=screenshot_path
                )

            # وضع الكود في المحرر
            await self.set_editor_code(solution_code)
            await asyncio.sleep(1)

            # النقر على زر التشغيل
            await self.click_run_button()
            await asyncio.sleep(4)

            # فحص إذا ظهرت رسالة اكتمال أو نافذة نجاح بعد التشغيل
            after_run_text = await self.page.evaluate("""() => document.body.innerText || "" """)
            if any(kw in after_run_text for kw in ["أحسنت", "تهانينا", "اكتمل المستوى"]):
                completion_screenshot = await self.take_screenshot("level_completed")
                await self.click_next_or_finish()
                await asyncio.sleep(2)
                await self.click_start_or_resume()
                return {
                    "success": True,
                    "type": "code",
                    "is_level_completed": True,
                    "summary": "🎉 تم حل التمرين البرمجي وإكمال المستوى!",
                    "code": solution_code,
                    "screenshot": completion_screenshot
                }

            # النقر على التالي إن ظهر لمتابعة الخطوات
            await self.click_next_or_finish()
            await asyncio.sleep(2)

            return {
                "success": True,
                "type": "code",
                "is_level_completed": False,
                "summary": summary,
                "code": solution_code,
                "screenshot": ""
            }

        # د. إذا كان سؤال اختيار من متعدد (Quiz / Comprehension Check)
        elif page_type == "quiz":
            clicked = await self.handle_quiz_options(gemini_solver, screenshot_path, page_text)
            await asyncio.sleep(2)
            await self.click_next_or_finish()

            # فحص إذا اكتمل المستوى بعد الكويز
            after_quiz_text = await self.page.evaluate("""() => document.body.innerText || "" """)
            is_comp = any(kw in after_quiz_text for kw in ["أحسنت", "تهانينا", "اكتمل المستوى"])

            return {
                "success": True,
                "type": "quiz",
                "is_level_completed": is_comp,
                "summary": summary,
                "screenshot": await self.take_screenshot("level_completed") if is_comp else ""
            }

        # هـ. محاولة النقر على زر 'ابدأ' أو أول درس متاح في قائمة الفصول
        if await self.click_start_or_resume():
            return {
                "success": True,
                "type": "general",
                "is_level_completed": False,
                "summary": "تم النقر على زر ابدأ / بدء التعلم",
                "screenshot": ""
            }

        if await self.click_active_lesson_card():
            return {
                "success": True,
                "type": "general",
                "is_level_completed": False,
                "summary": "تم فتح الدرس المتاح من قائمة الفصول",
                "screenshot": ""
            }

        # و. إذا وجد زر تشغيل أو التالي افتراضياً، انقر عليه
        next_clicked = await self.click_next_or_finish()
        if not next_clicked:
            await self.click_run_button()

        await asyncio.sleep(2)
        return {
            "success": True,
            "type": "general",
            "is_level_completed": False,
            "summary": summary or "تم فحص الصفحة ومحاولة التقدم.",
            "screenshot": ""
        }

    async def get_editor_code(self) -> Optional[str]:
        """استخراج الكود المكتوب في محرر الصفحة إن وجد"""
        try:
            code = await self.page.evaluate("""() => {
                // 1. Monaco Editor
                if (window.monaco && window.monaco.editor) {
                    const models = window.monaco.editor.getModels();
                    if (models && models.length > 0) {
                        return models[0].getValue();
                    }
                }
                // 2. Ace Editor
                if (window.ace) {
                    const el = document.querySelector('.ace_editor');
                    if (el && window.ace.edit) {
                        return window.ace.edit(el).getValue();
                    }
                }
                // 3. Textarea
                const ta = document.querySelector('textarea.code-editor, textarea');
                if (ta && ta.value) {
                    return ta.value;
                }
                return null;
            }""")
            return code
        except Exception:
            return None

    async def set_editor_code(self, new_code: str) -> bool:
        """كتابة الكود الجديد داخل المحرر"""
        try:
            # محاولة عبر Monaco و Ace في الجافاسكريبت مباشرة
            result = await self.page.evaluate("""(code) => {
                if (window.monaco && window.monaco.editor) {
                    const models = window.monaco.editor.getModels();
                    if (models && models.length > 0) {
                        models[0].setValue(code);
                        return true;
                    }
                }
                if (window.ace) {
                    const el = document.querySelector('.ace_editor');
                    if (el && window.ace.edit) {
                        window.ace.edit(el).setValue(code, 1);
                        return true;
                    }
                }
                const ta = document.querySelector('textarea');
                if (ta) {
                    ta.value = code;
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            }""", new_code)

            if result:
                return True

            # إذا لم تنجح الـ evaluate، نقوم بالتركيز على المحرر وكتابة الكود بمحاكاة بشرية
            editor_selectors = ['.monaco-editor', '.ace_editor', 'textarea', '[contenteditable="true"]']
            for sel in editor_selectors:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await self.human_click(el)
                    await self.page.keyboard.press("Control+A")
                    await self.page.keyboard.press("Backspace")
                    await self.human_delay(0.2, 0.5)
                    await self.human_type(new_code)
                    return True

            return False
        except Exception as e:
            print(f"Error setting code in editor: {e}")
            return False

    async def click_run_button(self) -> bool:
        """النقر على زر التشغيل (Run) بمحاكاة حركة الماوس البشرية"""
        # 1. البحث النصي الذكي أولاً
        if await self.click_element_by_text(["تشغيل", "Run", "تنفيذ", "Run Code"]):
            return True

        # 2. محددات الأزرار والـ SVG
        run_selectors = [
            'button:has-text("تشغيل")',
            'button:has-text("Run")',
            'button:has-text("تنفيذ")',
            '.run-button',
            '#run-button',
            '.play-button',
            'button[aria-label*="run" i]',
            'button[aria-label*="تشغيل"]',
            'button[title*="run" i]',
            'button[title*="تشغيل"]',
            'button:has(svg.fa-play)',
            'button:has(svg[data-icon="play"])',
            'button:has(i.fa-play)'
        ]
        for sel in run_selectors:
            btn = await self.page.query_selector(sel)
            if btn and await btn.is_visible():
                await self.human_delay(0.3, 0.7)
                await self.human_click(btn)
                return True
        return False

    async def click_next_or_finish(self) -> bool:
        """النقر على زر التالي أو إنهاء أو متابعة بحركة ماوس طبيعية"""
        # 1. البحث النصي الذكي
        if await self.click_element_by_text([
            "المستوى التالي",
            "التالي",
            "Next",
            "متابعة",
            "إنهاء",
            "حسنًا",
            "OK",
            "استمرار",
            "تخطي"
        ]):
            return True

        # 2. محددات الأزرار
        next_selectors = [
            'button:has-text("التالي")',
            'button:has-text("Next")',
            'button:has-text("متابعة")',
            'button:has-text("إنهاء")',
            'button:has-text("المستوى التالي")',
            'button:has-text("حسنًا")',
            'button:has-text("OK")',
            '.next-button',
            '#next-button',
            '.btn-next'
        ]
        for sel in next_selectors:
            btn = await self.page.query_selector(sel)
            if btn and await btn.is_visible():
                await self.human_delay(0.4, 0.8)
                await self.human_click(btn)
                return True
        return False

    async def handle_quiz_options(self, gemini_solver: GeminiSolver, screenshot_path: str, page_text: str) -> bool:
        """اختيار الخيار الصحيح في الكويز بمحاكاة طالب يقرأ ويفكر ويضغط"""
        try:
            # تمرير خفيف بالماوس لأسفل لرؤية الخيارات مثل الإنسان
            await self.human_scroll("down", steps=2)

            # البحث عن عناصر الخيارات
            option_buttons = await self.page.query_selector_all('button.choice, .quiz-choice, .option-item, [role="radio"]')
            if option_buttons:
                options_text = []
                for b in option_buttons:
                    txt = await b.text_content()
                    options_text.append(txt.strip() if txt else "")

                # سؤال Gemini عن الخيار الصحيح
                correct_idx = await gemini_solver.solve_quiz_question(
                    question=page_text[:500],
                    options=options_text,
                    screenshot_path=screenshot_path
                )

                # فترة تفكير وقراءة الخيارات طبيعية (Human Hesitation)
                await self.human_delay(1.2, 2.4)

                if 0 <= correct_idx < len(option_buttons):
                    # تحريك الماوس بسلاسة والضغط على الإجابة
                    await self.human_click(option_buttons[correct_idx])
                    await self.human_delay(0.4, 0.9)

            # النقر على زر فحص / إرسال بحركة طبيعية
            check_btn = await self.page.query_selector('button:has-text("فحص"), button:has-text("Check"), button:has-text("إرسال")')
            if check_btn and await check_btn.is_visible():
                await self.human_delay(0.3, 0.7)
                await self.human_click(check_btn)
                return True

            return False
        except Exception as e:
            print(f"Error handling quiz: {e}")
            return False
