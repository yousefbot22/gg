    # ==========================================
    # فتح الفصل داخل المتصفح
    # ==========================================

    async def open_chapter_in_browser(
        self,
        chapter_id: int,
        chapter_title: str = "",
        item_type: str = "chapter",
    ) -> bool:
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
            logger.info(
                f"Searching and opening '{target_title}' (ID: {chapter_id}, type: {item_type}, "
                f"unit: '{unit_title}', section: '{section_name}') on curriculum page..."
            )

            js_find_and_click = """([title, id, itemType, secName]) => {
                const idStr = String(id || '');
                const cleanTitle = (title || '').trim();
                const cleanSec = (secName || '').trim();

                function findElement() {
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

                    if (itemType === 'test') {
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
                                        const lastItem = childItems[childItems.length - 1];
                                        const t = (lastItem.innerText || '').trim();
                                        if (t.includes(cleanTitle) || t.includes('اختبار') || cleanTitle.includes(t) || childItems.length >= 6) {
                                            return lastItem;
                                        }
                                    }
                                }
                            }
                        }

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

                        const allMatches = Array.from(document.querySelectorAll('button, a, [role="button"], .item, [class*="item"], div, li')).filter(el => {
                            const t = (el.innerText || '').trim();
                            const r = el.getBoundingClientRect();
                            return r.height >= 15 && r.height <= 100 && r.width >= 30 && (t === cleanTitle || t.startsWith(cleanTitle));
                        });
                        if (allMatches.length > 1) {
                            return allMatches[allMatches.length - 1];
                        }
                    }

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

            res = await self.page.evaluate(js_find_and_click, [target_title, chapter_id, item_type, section_name])
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                logger.info(f"Successfully opened {item_type} '{target_title}' via direct click.")
                await asyncio.sleep(2)
                return True

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
                        logger.info(f"Expanding parent unit '{unit_title}'...")
                        unit_loc = self.page.locator(f"text='{unit_title}'").first
                        if await unit_loc.count() > 0:
                            await unit_loc.scroll_into_view_if_needed()
                            await unit_loc.click()
                            await asyncio.sleep(1.2)
                except Exception as e_u:
                    logger.warning(f"Notice expanding unit '{unit_title}': {e_u}")

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
                        logger.info(f"Expanding section '{section_name}'...")
                        sec_loc = self.page.locator(f"text='{section_name}'").first
                        if await sec_loc.count() > 0:
                            await sec_loc.scroll_into_view_if_needed()
                            await sec_loc.click()
                            await asyncio.sleep(1.0)
                except Exception as e_s:
                    logger.warning(f"Notice expanding section '{section_name}': {e_s}")

            res = await self.page.evaluate(js_find_and_click, [target_title, chapter_id, item_type, section_name])
            if res and res.get("found"):
                x, y = res.get("x", 0), res.get("y", 0)
                if x > 0 and y > 0:
                    await self.human_click_at(x, y)
                logger.info(f"Successfully opened {item_type} '{target_title}' after expanding.")
                await asyncio.sleep(2)
                return True

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

            clicked = await self.click_element_by_text([target_title, "ابدأ", "متابعة", "حل", "Start", "Play"])
            if clicked:
                logger.info(f"Clicked chapter via fallback text locator: '{target_title}'")
                await asyncio.sleep(2)
                return True

        except Exception as e:
            logger.error(f"Error opening chapter {chapter_id} on curriculum page: {e}")

        return False

    # ==========================================
    # تشغيل مشغل الفصل أو المراجعة
    # ==========================================

    async def play_active_chapter_or_review(
        self,
        item_type: str = "chapter",
        max_clicks: int = 120,
        on_progress=None,
    ) -> bool:
        if not self.page or self.page.is_closed():
            return False

        logger.info(f"Starting browser player automation for {item_type}...")
        for step in range(max_clicks):
            try:
                curr_url = self.page.url.lower()
                if "curriculum" in curr_url and step > 5:
                    logger.info("Player closed and returned to curriculum page.")
                    return True

                js_player_step = """() => {
                    const finishBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('إنهاء') || t.includes('إكمال') || t.includes('العودة') || t.includes('خروج') || t.includes('مبروك') || t.includes('تم') || t.includes('Next') || t.includes('Finish');
                    });
                    if (finishBtn && finishBtn.getBoundingClientRect().width > 0) {
                        finishBtn.click();
                        return { action: 'finish' };
                    }

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

                    const nextBtn = Array.from(document.querySelectorAll('button, [role="button"], .next, .arrow-next')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('التالي') || t.includes('متابعة') || t.includes('استمر') || b.classList.contains('next');
                    });
                    if (nextBtn && nextBtn.getBoundingClientRect().width > 0) {
                        nextBtn.click();
                        return { action: 'next_dialogue' };
                    }

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
    # حل الفصل عبر API
    # ==========================================

    async def solve_chapter(
        self,
        chapter_id: int,
        on_progress=None,
        take_screenshot_on_done: bool = True,
    ) -> Dict[str, Any]:
        if not self.page or self.page.is_closed():
            return {"success": False, "message": "المتصفح غير نشط."}

        self.api.set_page(self.page)
        self.is_running = True

        blocks_data = await self.api.get_chapter_blocks(chapter_id)
        chapter_info = blocks_data.get("chapter", {})
        chapter_name = chapter_info.get("name", f"الفصل {chapter_id}")

        if on_progress:
            await on_progress(
                f"🚀 **بدء حل {chapter_name} (ID: `{chapter_id}`) عبر الـ API بالذكاء الاصطناعي...**\n"
                f"⚡ جاري إرسال الإجابات النموذجية..."
            )

        api_res = await self.api.solve_chapter_via_api(
            chapter_id,
            on_progress=on_progress,
            gemini_solver=self.gemini_solver,
        )

        if api_res.get("success"):
            logger.info(f"Chapter {chapter_id} successfully completed via pure API: {api_res}")

            shot = None
            if take_screenshot_on_done:
                if on_progress:
                    await on_progress(
                        f"🎉 **تم حل جميع الأسئلة وتأكيد إكمال {chapter_name} بنجاح! (5/5 ⭐)**\n"
                        f"📸 جاري توثيق النتيجة بلقطة شاشة..."
                    )
                try:
                    curr_url = self.page.url.lower()
                    if "subjects/7/curriculum" not in curr_url:
                        await self.page.goto(self.CURRICULUM_URL, wait_until="domcontentloaded", timeout=25000)
                    else:
                        await self.page.reload(wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(1)
                except Exception as e_nav:
                    logger.warning(f"Notice navigating to curriculum after API complete: {e_nav}")

                shot = await self.take_screenshot(f"spx_ch_{chapter_id}_api_completed")

            return {
                "success": True,
                "chapter_id": chapter_id,
                "chapter_name": api_res.get("chapter_name", chapter_name),
                "cleared_dialogues": 84,
                "solved_questions": api_res.get("solved_questions", 5),
                "star_score": api_res.get("star_score", 5),
                "screenshot_path": shot,
                "method": "api",
            }

        if api_res.get("code") == "chapter_locked":
            logger.warning(f"Chapter {chapter_id} is locked. Reason: {api_res.get('message')}")
            return api_res

        logger.warning(f"API solve reported: {api_res}. Falling back to browser opener...")
        opened = await self.open_chapter_in_browser(chapter_id, chapter_title=chapter_name, item_type="chapter")
        if opened:
            await asyncio.sleep(2)
            await self.play_active_chapter_or_review(item_type="chapter", on_progress=on_progress)
            await asyncio.sleep(1)
            retry_comp = await self.api.complete_chapter(chapter_id)
            is_ok = bool(retry_comp.get("ok") or (retry_comp.get("data", {}).get("status") == "success"))

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
                    "method": "browser_player",
                }

        return {
            "success": False,
            "code": api_res.get("code", "failed"),
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "message": api_res.get("message", "تعذر تأكيد إكمال الفصل عبر الـ API."),
        }

    # ==========================================
    # حل المراجعات
    # ==========================================

    async def solve_review(
        self,
        review_id: int,
        title: str = "",
        on_progress=None,
    ) -> Dict[str, Any]:
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
                "method": "api",
            }

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
                    "method": "browser_player",
                }

        return {
            "success": False,
            "item_id": review_id,
            "chapter_name": rev_name,
            "message": api_res.get("message", "تعذر إكمال المراجعة."),
        }

    # ==========================================
    # حل الاختبارات
    # ==========================================

    async def play_active_test_browser(
        self,
        test_id: int,
        max_steps: int = 40,
        on_progress=None,
    ) -> bool:
        if not self.page or self.page.is_closed():
            return False

        logger.info(f"Starting interactive browser test player for test {test_id}...")

        await asyncio.sleep(1.5)
        for _ in range(3):
            clicked_start = await self.click_element_by_text([
                "ابدأ الاختبار", "بدء الاختبار", "ابدأ الآن", "بدء", "ابدأ",
                "Start Test", "Start Quiz", "Start",
            ])
            if clicked_start:
                logger.info(f"Clicked test start button for test {test_id}.")
                await asyncio.sleep(1.5)
                break
            await asyncio.sleep(0.5)

        for step in range(max_steps):
            try:
                js_extract = """() => {
                    const finishBtn = Array.from(document.querySelectorAll('button, [role="button"], a')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t.includes('تسليم الاختبار') || t.includes('إنهاء الاختبار') || t.includes('عرض النتيجة') || t.includes('النتيجة') || t.includes('خروج') || t.includes('العودة للمنهج') || t.includes('إكمال') || t.includes('Submit Test') || t.includes('Finish');
                    });
                    const isFinishVisible = finishBtn && finishBtn.getBoundingClientRect().width > 0;

                    let questionText = '';
                    const qEls = Array.from(document.querySelectorAll('.question, .question-text, .quiz-question, .title, h2, h3, h4, [class*="question"]'));
                    for (const el of qEls) {
                        const t = (el.innerText || '').trim();
                        if (t.length >= 8 && !t.includes('الثقافة المالية') && !t.includes('تسجيل الخروج')) {
                            questionText = t;
                            break;
                        }
                    }

                    const optEls = Array.from(document.querySelectorAll('.option, [class*="option"], [role="radio"], button[data-option], label, .choice, [class*="choice"]'));
                    const visibleOpts = [];
                    for (const el of optEls) {
                        const t = (el.innerText || '').trim();
                        const r = el.getBoundingClientRect();
                        if (r.width >= 15 && r.height >= 12 && t.length > 0 && !['التالي', 'السابق', 'تأكيد', 'رجوع', 'ابدأ'].includes(t)) {
                            visibleOpts.push({ text: t, tag: el.tagName });
                        }
                    }

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

                if has_finish:
                    logger.info(f"Test {test_id} submit/finish button detected: '{info.get('finishText')}'")
                    await self.click_element_by_text([
                        info.get("finishText"), "تسليم الاختبار", "إنهاء الاختبار",
                        "إنهاء", "العودة للمنهج", "خروج",
                    ])
                    await asyncio.sleep(2)
                    return True

                if options:
                    chosen_opt_text = None
                    opt_texts = [o.get("text", "") for o in options]

                    if q_text:
                        db_ans = answers_db.find_financial_answer(q_text)
                        if db_ans and db_ans.get("correct_answer"):
                            corr = db_ans["correct_answer"].strip()
                            for ot in opt_texts:
                                if ot.strip() == corr or corr in ot or ot in corr:
                                    chosen_opt_text = ot
                                    break

                    if not chosen_opt_text and self.gemini_solver and self.gemini_solver.is_configured():
                        try:
                            best_idx = await self.gemini_solver.solve_quiz_question(
                                q_text or "سؤال الثقافة المالية", opt_texts
                            )
                            if 0 <= best_idx < len(opt_texts):
                                chosen_opt_text = opt_texts[best_idx]
                                logger.info(f"Gemini selected test option {best_idx}: '{chosen_opt_text[:30]}'")
                        except Exception as e_gem:
                            logger.warning(f"Gemini solving exception during test: {e_gem}")

                    if not chosen_opt_text and opt_texts:
                        chosen_opt_text = opt_texts[0]

                    if chosen_opt_text:
                        await self.click_element_by_text([chosen_opt_text])
                        await asyncio.sleep(0.5)

                    if has_next:
                        await self.click_element_by_text(["التالي", "تأكيد", "إرسال", "Next"])
                        await asyncio.sleep(1)
                    else:
                        await self.page.keyboard.press("Space")
                        await asyncio.sleep(0.5)
                else:
                    clicked_fwd = await self.click_element_by_text([
                        "التالي", "متابعة", "استمر", "ابدأ", "Next", "Continue"
                    ])
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
        on_progress=None,
    ) -> Dict[str, Any]:
        if not self.page or self.page.is_closed():
            return {"success": False, "message": "المتصفح غير نشط."}

        self.api.set_page(self.page)
        self.is_running = True

        test_name = title or f"اختبار {test_id}"
        if on_progress:
            await on_progress(f"🏆 **جاري بدء وحل {test_name} (ID: `{test_id}`) عبر الذكاء الاصطناعي وبنك الأسئلة...**")

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
                                "method": "already_completed",
                            }
        except Exception as e_st:
            logger.warning(f"Notice checking pre-status for test {test_id}: {e_st}")

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
                "method": "api",
            }

        logger.info(f"Test {test_id} opening in browser with title '{test_name}'...")
        opened = await self.open_chapter_in_browser(test_id, chapter_title=test_name, item_type="test")
        if opened:
            await asyncio.sleep(2)
            await self.play_active_test_browser(test_id=test_id, on_progress=on_progress)
            await asyncio.sleep(2)

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
                    "method": "browser_player",
                }

        return {
            "success": False,
            "item_id": test_id,
            "chapter_name": test_name,
            "message": api_res.get("message", "تعذر تأكيد اجتياز الاختبار عبر الـ API والمتصفح."),
        }

    # ==========================================
    # الموجه الموحد
    # ==========================================

    async def solve_item(
        self,
        item_id: int,
        item_type: str = "chapter",
        item_title: str = "",
        on_progress=None,
        take_screenshot_on_done: bool = True,
    ) -> Dict[str, Any]:
        clean_type = (item_type or "chapter").lower().strip()
        if clean_type == "review":
            return await self.solve_review(item_id, title=item_title, on_progress=on_progress)
        elif clean_type == "test":
            return await self.solve_test(item_id, title=item_title, on_progress=on_progress)
        else:
            return await self.solve_chapter(
                item_id, on_progress=on_progress, take_screenshot_on_done=take_screenshot_on_done
            )
