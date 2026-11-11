"""Standalone debug — logs in, inspects responses, tests solving.

Usage:
    python debug_solve.py <username> <password>
"""
import asyncio
import json
import sys

from src.config import settings
from src.solver.qureo_client import QureoClient


async def main(username: str, password: str):
    print("=" * 70)
    print("🔍 Qureo API Deep Inspection")
    print("=" * 70)

    client = QureoClient(user_id=99999)
    api = client.api

    try:
        # Login
        print(f"\n[1] Login as {username}...")
        ok, msg, _ = await client.login(username, password)
        if not ok:
            print(f"❌ {msg}")
            return
        print("✓ Login OK")

        # 1. Chapters
        course_id = settings.qureo_python_course_id
        chapters = await api.get_course_chapters(course_id)
        print(f"\n[2] Chapters: {len(chapters)}")

        # 2. Check dashboard to find INCOMPLETE chapters
        print("\n[3] Fetching dashboard to find progress...")
        dashboard = await api.get_student_dashboard_status(course_id)
        print(f"  total_chapters: {dashboard.get('total_chapters')}")
        print(f"  completed_count: {dashboard.get('completed_count')}")
        print(f"  remaining_count: {dashboard.get('remaining_count')}")
        current = dashboard.get("current_chapter")
        if current:
            print(f"  current_chapter: id={current.get('id')} seq={current.get('seq')} name={current.get('name')}")

        # Pick the FIRST incomplete chapter to test
        completed_ids = {c["id"] for c in dashboard.get("completed_chapters", [])}
        incomplete = [c for c in chapters if c["id"] not in completed_ids]

        print(f"\n[4] Incomplete chapters: {len(incomplete)}")
        if not incomplete:
            print("⚠️ All chapters completed — can't test solving.")
            return

        target = incomplete[0]
        cid = target["id"]
        test_type = target["test_type"]
        print(f"\n🎯 Testing chapter: {cid} ({target['name']}, {test_type})")

        # ---- 5. Inspect /students/chapters/{id}/lectures ----
        print("\n" + "=" * 70)
        print(f"RAW: GET /students/chapters/{cid}/lectures")
        print("=" * 70)
        res = await api._call(f"/students/chapters/{cid}/lectures")
        print(f"status: {res.get('status')}, ok: {res.get('ok')}")
        print(f"data:\n{json.dumps(res.get('data'), indent=2, ensure_ascii=False)[:1500]}")

        # ---- 6. Inspect /students/chapters/{id}/test ----
        print("\n" + "=" * 70)
        print(f"RAW: GET /students/chapters/{cid}/test")
        print("=" * 70)
        res = await api._call(f"/students/chapters/{cid}/test")
        print(f"status: {res.get('status')}, ok: {res.get('ok')}")
        print(f"data:\n{json.dumps(res.get('data'), indent=2, ensure_ascii=False)[:2000]}")

        # ---- 7. Try /students/chapters/{id}/review ----
        print("\n" + "=" * 70)
        print(f"RAW: GET /students/chapters/{cid}/review")
        print("=" * 70)
        res = await api._call(f"/students/chapters/{cid}/review")
        print(f"status: {res.get('status')}, ok: {res.get('ok')}")
        print(f"data:\n{json.dumps(res.get('data'), indent=2, ensure_ascii=False)[:2000]}")

        # ---- 8. Explore more endpoints ----
        print("\n" + "=" * 70)
        print("EXPLORING MORE ENDPOINTS")
        print("=" * 70)
        more_endpoints = [
            f"/students/chapters/{cid}",
            f"/students/chapters/{cid}/questions",
            f"/students/chapters/{cid}/{test_type}/questions",
            f"/students/chapters/{cid}/test-questions",
            f"/students/chapters/{cid}/review-questions",
            f"/students/chapters/{cid}/details",
            f"/chapters/{cid}/details",
            f"/chapters/{cid}/info",
            f"/students/chapters/{cid}/progress",
            f"/students/chapters/{cid}/start",
        ]
        for ep in more_endpoints:
            try:
                r = await api._call(ep)
                st = r.get("status", "?")
                data = r.get("data")
                if r.get("ok"):
                    if isinstance(data, list):
                        preview = f"list[{len(data)}]"
                    elif isinstance(data, dict):
                        preview = f"dict with keys: {list(data.keys())[:8]}"
                    else:
                        preview = str(data)[:80]
                    print(f"  ✓ {ep:55s} → {st} | {preview}")
                else:
                    print(f"  ✗ {ep:55s} → {st}")
            except Exception as e:
                print(f"  ✗ {ep:55s} → EXC: {e}")

        # ---- 9. Try to understand the test endpoint structure ----
        print("\n" + "=" * 70)
        print(f"DEEP INSPECTION of /students/chapters/{cid}/test")
        print("=" * 70)
        test_res = await api._call(f"/students/chapters/{cid}/test")
        if test_res.get("ok"):
            data = test_res.get("data", {})
            if isinstance(data, dict):
                print(f"  Top-level keys: {list(data.keys())}")
                # Recursively show structure
                def show_structure(obj, prefix="", max_depth=3):
                    if max_depth == 0:
                        return
                    if isinstance(obj, dict):
                        for k, v in list(obj.items())[:10]:
                            if isinstance(v, (dict, list)):
                                print(f"{prefix}{k}: {type(v).__name__}")
                                show_structure(v, prefix + "  ", max_depth - 1)
                            else:
                                print(f"{prefix}{k}: {str(v)[:80]}")
                    elif isinstance(obj, list):
                        print(f"{prefix}[list with {len(obj)} items]")
                        if obj:
                            show_structure(obj[0], prefix + "  ", max_depth - 1)
                show_structure(data)

    finally:
        await client.stop()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python debug_solve.py <username> <password>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))