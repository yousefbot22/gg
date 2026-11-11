    # ==========================================
    # فتح المسار والدروس
    # ==========================================

    async def close_free_editor_if_open(self) -> bool:
        if not self.page or self.page.is_closed():
            return False
        try:
            closed = await self.page.evaluate("""() => {
                if (document.body.innerText.includes("المحرر الحر")) {
                    const elements = Array.from(document.querySelectorAll('button, div, span, svg, a'));
                    for (const el of elements) {
                        const rect = el.getBoundingClientRect();
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
        await self.close_free_editor_if_open()
        targets = ["بدء التعلم", "ابدأ", "Start", "متابعة", "استئناف"]
        return await self.click_element_by_text(targets)

    async def select_course_card(self, course_name: str = "python") -> bool:
        if "python" in str(course_name).lower():
            targets = ["Python", "بايثون"]
        else:
            targets = ["JavaScript", "جافاسكريبت", "JS"]
        return await self.click_element_by_text(targets)

    async def click_active_lesson_card(self) -> bool:
        if not self.page or self.page.is_closed():
            return False

        lesson_keywords = [
            "التدرب على المتغيرات",
            "إسناد القيم إلى المتغيرات",
            "مراجعة",
            "التدرب",
            "التدريب",
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
                    if (rect.left < maxLeft && rect.width >= 120 && rect.width <= 520 && rect.height >= 30 && rect.height <= 120) {
                        const text = (el.innerText || "").trim();
                        if (!text || text.includes("سنتعلم") || text.includes("قائمة الفصول") || text.length > 70) continue;

                        const isLocked = el.querySelector('[class*="lock"]') !== null || text.includes('مقفل') || text.includes('🔒');
                        if (isLocked) continue;

                        const hasCheck = el.querySelector('svg, i, [class*="check"], [class*="done"]') !== null || text.includes('✓') || text.includes('✔');

                        cards.push({ el: el, text: text, completed: hasCheck, area: rect.width * rect.height });
                    }
                }

                if (cards.length > 0) {
                    const leafCards = cards.filter(c1 => !cards.some(c2 => c1 !== c2 && c1.el.contains(c2.el)));
                    const targetList = leafCards.length > 0 ? leafCards : cards;
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
        target_url = course_url or self.active_course_url
        self.active_course_url = target_url

        try:
            current_url = self.page.url if (self.page and not self.page.is_closed()) else ""

            if current_url and target_url in current_url:
                print(f"Browser is already at course page: {current_url}")
                await self.click_start_or_resume()
                return True, "المسار مفتوح وجاهز للحل.", ""

            print(f"Navigating to course: {target_url}")
            await self.page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)

            course_type = "python" if "python" in target_url.lower() else "javascript"
            await self.select_course_card(course_type)
            await asyncio.sleep(1.5)

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

    # ==========================================
    # حل الخطوة الحالية
    # ==========================================

    async def solve_current_step(self, gemini_solver: GeminiSolver) -> Dict[str, Any]:
        if not self.page:
            return {"success": False, "message": "المتصفح غير نشط."}

        await self.close_free_editor_if_open()

        if await self.click_start_or_resume():
            await asyncio.sleep(2)

        page_text = await self.page.evaluate("""() => document.body.innerText || "" """)

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
                "screenshot": completion_screenshot,
            }

        screenshot_path = await self.take_screenshot("step_attempt")
        current_editor_code = await self.get_editor_code()

        analysis = await gemini_solver.analyze_screen_and_guide(
            screenshot_path=screenshot_path,
            additional_context=page_text[:1500],
        )

        if screenshot_path and Path(screenshot_path).exists():
            try:
                Path(screenshot_path).unlink(missing_ok=True)
            except Exception:
                pass

        page_type = analysis.get("page_type", "unknown")
        summary = analysis.get("summary", "")

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
                "screenshot": completion_screenshot,
            }

        if page_type == "dashboard" or "بدء التعلم" in page_text or "ابدأ" in page_text:
            if await self.click_start_or_resume():
                return {
                    "success": True,
                    "type": "start",
                    "is_level_completed": False,
                    "summary": "تم النقر على زر ابدأ / بدء التعلم.",
                    "screenshot": "",
                }

        suggested_btn = analysis.get("next_button")
        if suggested_btn and str(suggested_btn).lower() not in ("null", "none", ""):
            print(f"Gemini suggested clicking: {suggested_btn}")
            if await self.click_element_by_text(suggested_btn):
                await asyncio.sleep(2.5)
                return {
                    "success": True,
                    "type": "general",
                    "is_level_completed": False,
                    "summary": f"تم النقر على: {suggested_btn}",
                    "screenshot": "",
                }

        if page_type == "chapter_map" or "قائمة الفصول" in page_text:
            print("Detected chapter/lessons view, searching for active lesson...")
            if await self.click_active_lesson_card():
                await asyncio.sleep(3)
                return {
                    "success": True,
                    "type": "chapter_map",
                    "is_level_completed": False,
                    "summary": "تم فتح الدرس المتاح من قائمة الفصول.",
                    "screenshot": "",
                }

        if page_type == "dialogue":
            await self.click_next_or_finish()
            await asyncio.sleep(2)
            return {
                "success": True,
                "type": "dialogue",
                "is_level_completed": False,
                "summary": "تم متابعة الحوار التعليمي.",
                "screenshot": "",
            }

        if page_type == "code_task" or current_editor_code is not None:
            solution_code = analysis.get("solution_code")
            if not solution_code:
                solution_code = await gemini_solver.solve_code_task(
                    instruction=summary or page_text[:800],
                    current_code=current_editor_code or "",
                    language="python" if "python" in self.active_course_url else "javascript",
                    screenshot_path=screenshot_path,
                )

            await self.set_editor_code(solution_code)
            await asyncio.sleep(1)
            await self.click_run_button()
            await asyncio.sleep(4)

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
                    "screenshot": completion_screenshot,
                }

            await self.click_next_or_finish()
            await asyncio.sleep(2)
            return {
                "success": True,
                "type": "code",
                "is_level_completed": False,
                "summary": summary,
                "code": solution_code,
                "screenshot": "",
            }

        elif page_type == "quiz":
            await self.handle_quiz_options(gemini_solver, screenshot_path, page_text)
            await asyncio.sleep(2)
            await self.click_next_or_finish()

            after_quiz_text = await self.page.evaluate("""() => document.body.innerText || "" """)
            is_comp = any(kw in after_quiz_text for kw in ["أحسنت", "تهانينا", "اكتمل المستوى"])

            return {
                "success": True,
                "type": "quiz",
                "is_level_completed": is_comp,
                "summary": summary,
                "screenshot": await self.take_screenshot("level_completed") if is_comp else "",
            }

        if await self.click_start_or_resume():
            return {
                "success": True,
                "type": "general",
                "is_level_completed": False,
                "summary": "تم النقر على زر ابدأ / بدء التعلم",
                "screenshot": "",
            }

        if await self.click_active_lesson_card():
            return {
                "success": True,
                "type": "general",
                "is_level_completed": False,
                "summary": "تم فتح الدرس المتاح من قائمة الفصول",
                "screenshot": "",
            }

        next_clicked = await self.click_next_or_finish()
        if not next_clicked:
            await self.click_run_button()

        await asyncio.sleep(2)
        return {
            "success": True,
            "type": "general",
            "is_level_completed": False,
            "summary": summary or "تم فحص الصفحة ومحاولة التقدم.",
            "screenshot": "",
        }

    async def get_editor_code(self) -> Optional[str]:
        try:
            code = await self.page.evaluate("""() => {
                if (window.monaco && window.monaco.editor) {
                    const models = window.monaco.editor.getModels();
                    if (models && models.length > 0) return models[0].getValue();
                }
                if (window.ace) {
                    const el = document.querySelector('.ace_editor');
                    if (el && window.ace.edit) return window.ace.edit(el).getValue();
                }
                const ta = document.querySelector('textarea.code-editor, textarea');
                if (ta && ta.value) return ta.value;
                return null;
            }""")
            return code
        except Exception:
            return None

    async def set_editor_code(self, new_code: str) -> bool:
        try:
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
        if await self.click_element_by_text(["تشغيل", "Run", "تنفيذ", "Run Code"]):
            return True

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
            'button:has(i.fa-play)',
        ]
        for sel in run_selectors:
            btn = await self.page.query_selector(sel)
            if btn and await btn.is_visible():
                await self.human_delay(0.3, 0.7)
                await self.human_click(btn)
                return True
        return False

    async def click_next_or_finish(self) -> bool:
        if await self.click_element_by_text([
            "المستوى التالي", "التالي", "Next", "متابعة", "إنهاء",
            "حسنًا", "OK", "استمرار", "تخطي",
        ]):
            return True

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
            '.btn-next',
        ]
        for sel in next_selectors:
            btn = await self.page.query_selector(sel)
            if btn and await btn.is_visible():
                await self.human_delay(0.4, 0.8)
                await self.human_click(btn)
                return True
        return False

    async def handle_quiz_options(self, gemini_solver: GeminiSolver, screenshot_path: str, page_text: str) -> bool:
        try:
            await self.human_scroll("down", steps=2)

            option_buttons = await self.page.query_selector_all(
                'button.choice, .quiz-choice, .option-item, [role="radio"]'
            )
            if option_buttons:
                options_text = []
                for b in option_buttons:
                    txt = await b.text_content()
                    options_text.append(txt.strip() if txt else "")

                correct_idx = await gemini_solver.solve_quiz_question(
                    question=page_text[:500],
                    options=options_text,
                    screenshot_path=screenshot_path,
                )

                await self.human_delay(1.2, 2.4)

                if 0 <= correct_idx < len(option_buttons):
                    await self.human_click(option_buttons[correct_idx])
                    await self.human_delay(0.4, 0.9)

            check_btn = await self.page.query_selector(
                'button:has-text("فحص"), button:has-text("Check"), button:has-text("إرسال")'
            )
            if check_btn and await check_btn.is_visible():
                await self.human_delay(0.3, 0.7)
                await self.human_click(check_btn)
                return True

            return False
        except Exception as e:
            print(f"Error handling quiz: {e}")
            return False
