#!/usr/bin/env python3
"""
End-to-End Chat Flow Multilingual Test:
Simulates a real conversation with alternating languages across multiple turns:
  Turn 1: English -> Answer must be in English.
  Turn 2: Telugu -> Answer must immediately switch to Telugu.
  Turn 3: Hindi -> Answer must immediately switch to Hindi.
  Turn 4: English with stale Hindi selector -> Answer must switch back to English.
  Turn 5: English with manual override to Telugu -> Answer must be in Telugu.
"""
import os
import sys
import io
import asyncio
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.chat_service import stream_chat_message
from app.services.language import detect_script_language

async def run_turn(message: str, conversation_id: str, user_id: str, language: str, override_language: bool = False):
    print(f"\n--- User Query: '{message}' (dropdown: '{language}', override: {override_language}) ---")
    chunks = []
    done_event = None
    async for event in stream_chat_message(
        message=message,
        conversation_id=conversation_id,
        language=language,
        user_id=user_id,
        override_language=override_language,
    ):
        if event["type"] == "chunk":
            chunks.append(event["text"])
        elif event["type"] == "done":
            done_event = event

    full_text = "".join(chunks)
    res_lang = done_event["language"]
    script = detect_script_language(full_text)
    print(f"Bot Response ({res_lang}, script: {script}):")
    print(f"  {full_text[:120]}...")
    return full_text, res_lang, done_event["conversation_id"]

async def main():
    user_id = f"test-user-{uuid.uuid4()}"
    conv_id = None

    # Turn 1: English
    t1_text, t1_lang, conv_id = await run_turn("What is Article 21?", conv_id, user_id, "English")
    assert t1_lang == "English", f"Expected English, got {t1_lang}"
    assert "personal liberty" in t1_text.lower(), "Expected Article 21 substance"

    # Turn 2: Telugu (same conversation)
    t2_text, t2_lang, _ = await run_turn("ఆర్టికల్ 21 ఏమిటి?", conv_id, user_id, "Auto-Detect")
    assert t2_lang == "Telugu", f"Expected Telugu, got {t2_lang}"
    assert "స్వేచ్ఛ" in t2_text or "ఆర్టికల్" in t2_text or detect_script_language(t2_text) == "Telugu", "Expected Telugu response"

    # Turn 3: Hindi (same conversation)
    t3_text, t3_lang, _ = await run_turn("अनुच्छेद 21A क्या है?", conv_id, user_id, "Auto-Detect")
    assert t3_lang == "Hindi", f"Expected Hindi, got {t3_lang}"
    assert "अनुच्छेद" in t3_text or "शिक्षा" in t3_text or detect_script_language(t3_text) == "Hindi", "Expected Hindi response"

    # Turn 4: English with stale Hindi selector (same conversation)
    t4_text, t4_lang, _ = await run_turn("What is Article 19?", conv_id, user_id, "Hindi", override_language=False)
    assert t4_lang == "English", f"Expected English despite stale Hindi dropdown, got {t4_lang}"
    assert "speech" in t4_text.lower() or "article 19" in t4_text.lower(), "Expected Article 19 substance"

    # Turn 5: Manual override to Telugu (same conversation)
    t5_text, t5_lang, _ = await run_turn("Explain Article 14", conv_id, user_id, "Telugu", override_language=True)
    assert t5_lang == "Telugu", f"Expected Telugu due to manual override, got {t5_lang}"
    assert detect_script_language(t5_text) == "Telugu" or "ఆర్టికల్" in t5_text, "Expected Telugu response"

    print("\n==================================================")
    print("ALL 5 MULTILINGUAL CONVERSATION TURNS PASSED 100%!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
