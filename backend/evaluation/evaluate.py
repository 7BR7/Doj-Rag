"""
RAG-DoJ Evaluation Framework
Runs evaluation questions against the live API and scores results.
Usage (from project root):
    backend\\venv\\Scripts\\python.exe backend/evaluation/evaluate.py
"""
import sys, os, json, time, re, asyncio, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx

API_BASE = "http://localhost:8000/api"
QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "evaluation_questions.json")


def contains_keywords(text: str, keywords: list[str]) -> float:
    """Return fraction of expected keywords found in the response text."""
    if not keywords:
        return 1.0  # No assertion = auto-pass
    text_lower = text.lower()
    found = sum(1 for kw in keywords if kw.lower() in text_lower)
    return found / len(keywords)


def score_hallucination(text: str, test_id: str, category: str) -> bool:
    """Return True if the response correctly refused to hallucinate for HALLUCINATION_TEST."""
    if category != "HALLUCINATION_TEST":
        return True
    refusal_phrases = [
        "could not find", "not found", "unavailable", "does not exist",
        "unable to locate", "no relevant", "i don't have", "section 999999"
    ]
    text_lower = text.lower()
    return any(p in text_lower for p in refusal_phrases)


async def get_answer(client: httpx.AsyncClient, question: str, session_id: str) -> dict:
    """Call the streaming chat endpoint and collect the final done event."""
    payload = {
        "message": question,
        "language": "English",
        "conversation_id": session_id,
    }
    full_text = ""
    done_data = {}
    try:
        async with client.stream(
            "POST", f"{API_BASE}/chat",
            json=payload, timeout=90.0,
            headers={"Content-Type": "application/json"}
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                ev = data.get("event", "")
                if ev == "token":
                    full_text += data.get("token", "")
                elif ev == "done":
                    done_data = data
    except Exception as exc:
        return {"text": "", "error": str(exc), "done_data": {}}
    return {"text": full_text, "error": None, "done_data": done_data}


async def run_evaluation(auth_token: str):
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    headers = {"Authorization": f"Bearer {auth_token}"}
    results = []
    total_keyword_score = 0.0
    total_hallucination_pass = 0
    evaluated = 0

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for q in questions:
            print(f"\n[{q['question_id']}] {q['category']}: {q['question'][:80]}")
            t0 = time.time()
            response = await get_answer(client, q["question"], f"eval_{q['question_id']}")
            latency = time.time() - t0

            answer_text = response["text"]
            if response["error"]:
                print(f"  ❌ Error: {response['error']}")
                results.append({**q, "status": "ERROR", "error": response["error"], "latency": latency})
                continue

            kw_score = contains_keywords(answer_text, q.get("expected_answer_contains", []))
            halluc_pass = score_hallucination(answer_text, q["question_id"], q["category"])
            done_data = response["done_data"]

            total_keyword_score += kw_score
            total_hallucination_pass += int(halluc_pass)
            evaluated += 1

            result = {
                **q,
                "status": "PASS" if (kw_score >= 0.5 and halluc_pass) else "FAIL",
                "keyword_score": round(kw_score, 3),
                "hallucination_pass": halluc_pass,
                "latency_s": round(latency, 2),
                "answer_snippet": answer_text[:300].replace("\n", " "),
                "sources_count": len(done_data.get("sources", [])),
                "intent": done_data.get("intent", ""),
                "why_this_answer": done_data.get("why_this_answer", {}).get("summary", ""),
                "citation_score": done_data.get("citation_verification", {}).get("support_score", None),
            }
            results.append(result)
            badge = "✅" if result["status"] == "PASS" else "⚠️"
            print(f"  {badge} kw={kw_score:.2f} | halluc={'OK' if halluc_pass else 'FAIL'} | {latency:.1f}s | intent={result['intent']}")
            print(f"  Answer: {answer_text[:120]}...")

    # Summary
    passed = sum(1 for r in results if r.get("status") == "PASS")
    errored = sum(1 for r in results if r.get("status") == "ERROR")
    avg_kw = total_keyword_score / max(evaluated, 1)
    halluc_rate = total_hallucination_pass / max(sum(1 for q in questions if q["category"] == "HALLUCINATION_TEST"), 1)

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print(f"  Total questions : {len(questions)}")
    print(f"  Evaluated       : {evaluated}")
    print(f"  Passed          : {passed}")
    print(f"  Failed          : {evaluated - passed}")
    print(f"  Errors          : {errored}")
    print(f"  Avg keyword score: {avg_kw:.3f}")
    print(f"  Hallucination prevention: {halluc_rate:.1%}")
    print("=" * 60)

    # Save results
    out_file = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(questions),
                "evaluated": evaluated,
                "passed": passed,
                "failed": evaluated - passed,
                "errored": errored,
                "avg_keyword_score": round(avg_kw, 4),
                "hallucination_prevention_rate": round(halluc_rate, 4),
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n📊 Full results saved to: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=False, default="",
                        help="JWT bearer token for auth. If empty, logs in with test credentials.")
    parser.add_argument("--username", default="testuser")
    parser.add_argument("--password", default="testpassword")
    args = parser.parse_args()

    token = args.token
    if not token:
        # Attempt login
        import httpx as _httpx
        try:
            resp = _httpx.post(
                f"{API_BASE}/auth/login",
                json={"username": args.username, "password": args.password},
                timeout=10
            )
            token = resp.json().get("access_token", "")
            if token:
                print(f"✅ Logged in as {args.username}")
            else:
                print("❌ Login failed — running without auth token (may fail on protected routes)")
        except Exception as e:
            print(f"⚠️  Login error: {e} — continuing without token")

    asyncio.run(run_evaluation(token))
