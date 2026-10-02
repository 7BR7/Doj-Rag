import { useCallback, useRef, useState, useEffect } from "react";
import { API_BASE } from "../services/api.js";
import { useI18n } from "../i18n.jsx";

// Display name -> BCP-47 locale
export const VOICE_LOCALES = {
  English: "en-IN",
  Hindi: "hi-IN",
  Tamil: "ta-IN",
  Telugu: "te-IN",
  Kannada: "kn-IN",
  Malayalam: "ml-IN",
  Bengali: "bn-IN",
  Marathi: "mr-IN",
  Gujarati: "gu-IN",
  Punjabi: "pa-IN",
  Odia: "or-IN",
  Urdu: "ur-IN",
};

export const LANG_CODES = {
  English: "en",
  Hindi: "hi",
  Tamil: "ta",
  Telugu: "te",
  Kannada: "kn",
  Malayalam: "ml",
  Bengali: "bn",
  Marathi: "mr",
  Gujarati: "gu",
  Punjabi: "pa",
  Odia: "or",
  Urdu: "ur",
};

/**
 * Detects the language script directly from Unicode codepoints in the text.
 * This guarantees that even if the language selector is set to "Auto-Detect"
 * or the stored language tag is missing, Indian script text (Telugu, Devanagari,
 * Tamil, Bengali, etc.) will ALWAYS be pronounced with the appropriate voice locale.
 */
export function detectScriptLocale(text) {
  if (!text) return null;
  if (/[\u0C00-\u0C7F]/.test(text)) return { language: "Telugu", locale: "te-IN", code: "te" };
  if (/[\u0B80-\u0BFF]/.test(text)) return { language: "Tamil", locale: "ta-IN", code: "ta" };
  if (/[\u0C80-\u0CFF]/.test(text)) return { language: "Kannada", locale: "kn-IN", code: "kn" };
  if (/[\u0D00-\u0D7F]/.test(text)) return { language: "Malayalam", locale: "ml-IN", code: "ml" };
  if (/[\u0980-\u09FF]/.test(text)) return { language: "Bengali", locale: "bn-IN", code: "bn" };
  if (/[\u0A80-\u0AFF]/.test(text)) return { language: "Gujarati", locale: "gu-IN", code: "gu" };
  if (/[\u0A00-\u0A7F]/.test(text)) return { language: "Punjabi", locale: "pa-IN", code: "pa" };
  if (/[\u0B00-\u0B7F]/.test(text)) return { language: "Odia", locale: "or-IN", code: "or" };
  if (/[\u0600-\u06FF]/.test(text)) return { language: "Urdu", locale: "ur-IN", code: "ur" };
  if (/[\u0900-\u097F]/.test(text)) return { language: "Hindi", locale: "hi-IN", code: "hi" };
  return null;
}

/**
 * Cleans markdown formatting, symbols, and citations that cause speech engines
 * to stutter or read out punctuation tags.
 */
export function cleanTextForSpeech(text) {
  if (!text) return "";
  return text
    .replace(/^#+\s+/gm, "")             // headers
    .replace(/\*\*([^*]+)\*\*/g, "$1")  // bold
    .replace(/\*([^*]+)\*/g, "$1")      // italics
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/`([^`]+)`/g, "$1")        // backticks
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // markdown links
    .replace(/\[\d+\]/g, "")            // footnotes / citations [1]
    .replace(/^\s*[-*+]\s+/gm, "")      // bullet points
    .replace(/^\s*\d+\.\s+/gm, "")      // numbered items
    .replace(/[—–]/g, ", ")             // dashes to natural pause
    .replace(/\s{2,}/g, " ")            // extra whitespace
    .trim();
}

/**
 * Splits text into sentence-sized chunks (<= 150 chars) so Chromium's speech
 * engine does not time out or drop audio on long Indian utterances.
 */
export function splitIntoSentences(text) {
  if (!text) return [];
  const regex = /([^।\.\?\!\n;]+[।\.\?\!\n;]*)/g;
  const matches = text.match(regex) || [text];
  const chunks = [];
  let buffer = "";

  for (const part of matches) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    if (buffer && buffer.length + trimmed.length > 150) {
      chunks.push(buffer.trim());
      buffer = trimmed;
    } else {
      buffer = buffer ? `${buffer} ${trimmed}` : trimmed;
    }
  }
  if (buffer.trim()) {
    chunks.push(buffer.trim());
  }
  return chunks.length > 0 ? chunks : [text];
}

let cachedVoices = [];

function loadVoices() {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) {
      resolve([]);
      return;
    }
    const current = window.speechSynthesis.getVoices();
    if (current.length > 0) {
      cachedVoices = current;
      resolve(current);
      return;
    }
    const handler = () => {
      window.speechSynthesis.removeEventListener("voiceschanged", handler);
      cachedVoices = window.speechSynthesis.getVoices();
      resolve(cachedVoices);
    };
    window.speechSynthesis.addEventListener("voiceschanged", handler);

    // Polling fallback up to 2 seconds for Chrome/Edge
    let checks = 0;
    const interval = setInterval(() => {
      checks++;
      const v = window.speechSynthesis.getVoices();
      if (v.length > 0) {
        clearInterval(interval);
        window.speechSynthesis.removeEventListener("voiceschanged", handler);
        cachedVoices = v;
        resolve(v);
      } else if (checks > 10) {
        clearInterval(interval);
        resolve([]);
      }
    }, 200);
  });
}

function findVoiceForLocale(voices, localePrefix, languageName) {
  if (!voices || voices.length === 0) return null;
  const targetLocale = (localePrefix || "en-IN").toLowerCase().replace("_", "-");
  const langCode = targetLocale.split("-")[0];
  const langLower = (languageName || "").toLowerCase();

  // 1. Exact BCP-47 match: e.g. "te-in", "hi-in", "ta-in"
  let match = voices.find((v) => (v.lang || "").toLowerCase().replace("_", "-") === targetLocale);
  if (match) return match;

  // 2. Language code prefix: e.g. "te", "te-*"
  match = voices.find((v) => {
    const vLang = (v.lang || "").toLowerCase().replace("_", "-");
    return vLang.startsWith(langCode + "-") || vLang === langCode;
  });
  if (match) return match;

  // 3. Name match: check if voice.name contains language name
  if (langLower && langLower !== "english") {
    match = voices.find((v) => (v.name || "").toLowerCase().includes(langLower));
    if (match) return match;
  }

  // 4. Native language script / name keywords in voice.name
  const NATIVE_KEYWORDS = {
    Telugu: ["telugu", "తెలుగు", "shruti", "mohan"],
    Hindi: ["hindi", "हिन्दी", "swara", "madhur", "kalpana", "hemant"],
    Tamil: ["tamil", "தமிழ்", "valluvar"],
    Kannada: ["kannada", "ಕನ್ನಡ", "gagan"],
    Malayalam: ["malayalam", "മലയാളം", "midhun"],
    Bengali: ["bengali", "বাংলা", "bangla", "bashkar", "tanishaa"],
    Marathi: ["marathi", "मराठी", "aarohi", "manohar"],
    Gujarati: ["gujarati", "ગુજરાતી", "niranjan", "dhwani"],
    Punjabi: ["punjabi", "ਪੰਜਾਬੀ", "gurpreet"],
    Odia: ["odia", "oriya", "ଓଡ଼ିଆ"],
    Urdu: ["urdu", "اردو", "salman", "gul"],
  };

  const kwList = NATIVE_KEYWORDS[languageName] || [];
  for (const kw of kwList) {
    match = voices.find((v) => (v.name || "").toLowerCase().includes(kw));
    if (match) return match;
  }

  // 5. Fallback Indian accent voice for clear pronunciation of Indian names and legal terms
  match = voices.find((v) => {
    const vLang = (v.lang || "").toLowerCase().replace("_", "-");
    const vName = (v.name || "").toLowerCase();
    return vLang === "en-in" || vName.includes("india") || vName.includes("heera") || vName.includes("ravi") || vName.includes("neerja");
  });
  if (match) return match;

  // 6. Browser default voice
  return voices.find((v) => v.default) || voices[0] || null;
}

/** Dual text-to-speech engine: high-fidelity Indic voice stream via /api/tts + browser SpeechSynthesis fallback. */
export function useTextToSpeech() {
  const { t } = useI18n();
  const [speakingId, setSpeakingId] = useState(null);
  const [unavailableNotice, setUnavailableNotice] = useState(null);
  const activeSessionRef = useRef(0);
  const keepAliveIntervalRef = useRef(null);
  const lastUtteranceRef = useRef(null);
  const currentAudioRef = useRef(null);

  const stop = useCallback(() => {
    activeSessionRef.current += 1;
    if (keepAliveIntervalRef.current) {
      clearInterval(keepAliveIntervalRef.current);
      keepAliveIntervalRef.current = null;
    }
    if (currentAudioRef.current) {
      try {
        currentAudioRef.current.pause();
        currentAudioRef.current.currentTime = 0;
        currentAudioRef.current.src = "";
      } catch (_) {}
      currentAudioRef.current = null;
    }
    if ("speechSynthesis" in window) {
      try {
        window.speechSynthesis.cancel();
      } catch (_) {}
    }
    setSpeakingId(null);
  }, []);

  const speak = useCallback(async (rawText, language, id) => {
    stop();
    setUnavailableNotice(null);

    const sessionId = ++activeSessionRef.current;
    const cleanedText = cleanTextForSpeech(rawText);
    if (!cleanedText) return;

    lastUtteranceRef.current = { rawText, language, id };

    // Detect script directly from Unicode characters in the text
    const detected = detectScriptLocale(cleanedText);
    const resolvedLanguage = detected ? detected.language : (language || "English");
    const langCode = detected ? detected.code : (LANG_CODES[resolvedLanguage] || "en");
    const locale = detected ? detected.locale : (VOICE_LOCALES[resolvedLanguage] || "en-IN");

    const chunks = splitIntoSentences(cleanedText);
    if (chunks.length === 0) return;

    setSpeakingId(id);

    // Strategy 1: For non-English Indian languages (Tamil, Telugu, Hindi, etc.),
    // Windows standard installations lack native SAPI Indic voices, which causes
    // SpeechSynthesis to fail silently. We stream from high-fidelity /api/tts endpoint.
    if (langCode !== "en") {
      let chunkIdx = 0;

      const fallbackToSpeechSynthesis = async () => {
        if (!("speechSynthesis" in window)) {
          setUnavailableNotice(t("ttsUnsupported"));
          setSpeakingId(null);
          return;
        }
        const voices = await loadVoices();
        if (activeSessionRef.current !== sessionId) return;
        const voice = findVoiceForLocale(voices, locale, resolvedLanguage);
        playSpeechSynthesisChunks(chunks, locale, voice, sessionId);
      };

      const playNextAudioChunk = () => {
        if (activeSessionRef.current !== sessionId || chunkIdx >= chunks.length) {
          if (activeSessionRef.current === sessionId) setSpeakingId(null);
          return;
        }

        const chunk = chunks[chunkIdx++];
        const ttsUrl = `${API_BASE}/api/tts?text=${encodeURIComponent(chunk)}&lang=${langCode}`;
        const audio = new Audio(ttsUrl);
        currentAudioRef.current = audio;

        audio.onended = () => {
          if (activeSessionRef.current === sessionId) {
            playNextAudioChunk();
          }
        };

        audio.onerror = () => {
          console.warn("Backend TTS stream failed, attempting browser SpeechSynthesis fallback");
          fallbackToSpeechSynthesis();
        };

        audio.play().catch(() => {
          fallbackToSpeechSynthesis();
        });
      };

      playNextAudioChunk();
      return;
    }

    // Strategy 2: For English, browser SpeechSynthesis provides instant zero-network playback.
    if (!("speechSynthesis" in window)) {
      setUnavailableNotice(t("ttsUnsupported"));
      setSpeakingId(null);
      return;
    }

    const voices = await loadVoices();
    if (activeSessionRef.current !== sessionId) return;

    const voice = findVoiceForLocale(voices, locale, resolvedLanguage);
    playSpeechSynthesisChunks(chunks, locale, voice, sessionId);
  }, [stop, t]);

  const playSpeechSynthesisChunks = (chunks, locale, voice, sessionId) => {
    // Keepalive for Chromium audio GC bug
    keepAliveIntervalRef.current = setInterval(() => {
      if (window.speechSynthesis.speaking) {
        window.speechSynthesis.pause();
        window.speechSynthesis.resume();
      }
    }, 4000);

    let chunkIndex = 0;

    const playNext = () => {
      if (activeSessionRef.current !== sessionId || chunkIndex >= chunks.length) {
        if (keepAliveIntervalRef.current) {
          clearInterval(keepAliveIntervalRef.current);
          keepAliveIntervalRef.current = null;
        }
        if (activeSessionRef.current === sessionId) setSpeakingId(null);
        return;
      }

      const chunkText = chunks[chunkIndex++];
      const utterance = new SpeechSynthesisUtterance(chunkText);
      utterance.lang = locale;
      if (voice) utterance.voice = voice;
      utterance.rate = 1.0;
      utterance.pitch = 1.0;

      utterance.onend = () => {
        if (activeSessionRef.current === sessionId) playNext();
      };

      utterance.onerror = () => {
        if (activeSessionRef.current === sessionId) playNext();
      };

      window.speechSynthesis.speak(utterance);
    };

    window.speechSynthesis.resume();
    playNext();
  };

  const replay = useCallback(() => {
    if (lastUtteranceRef.current) {
      const { rawText, language, id } = lastUtteranceRef.current;
      speak(rawText, language, id);
    }
  }, [speak]);

  useEffect(() => {
    return () => {
      if (keepAliveIntervalRef.current) {
        clearInterval(keepAliveIntervalRef.current);
      }
      if (currentAudioRef.current) {
        try {
          currentAudioRef.current.pause();
          currentAudioRef.current.src = "";
        } catch (_) {}
      }
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return { speak, stop, replay, speakingId, unavailableNotice };
}

/** Microphone recording with real-time Web Speech API + Faster-Whisper fallback. */
export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const recognitionRef = useRef(null);
  const liveTranscriptRef = useRef("");

  const start = useCallback(async (requestedLanguage) => {
    setError(null);
    liveTranscriptRef.current = "";

    // 1. Try starting Web Speech API for instant zero-latency speech recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        const recognition = new SpeechRecognition();
        const locale = (requestedLanguage && VOICE_LOCALES[requestedLanguage]) || "en-IN";
        recognition.lang = locale;
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event) => {
          let full = "";
          for (let i = 0; i < event.results.length; i++) {
            full += event.results[i][0].transcript + " ";
          }
          liveTranscriptRef.current = full.trim();
        };

        recognition.onerror = () => {
          // Non-fatal: MediaRecorder will still capture audio for Faster-Whisper
        };

        recognition.start();
        recognitionRef.current = recognition;
      } catch (_) {
        recognitionRef.current = null;
      }
    }

    // 2. Start MediaRecorder as audio backup
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
        recognitionRef.current = null;
      }
      setError("Microphone access was denied or is unavailable.");
      setIsRecording(false);
    }
  }, []);

  const stop = useCallback(() => {
    return new Promise((resolve) => {
      // Stop recognition if active
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
        recognitionRef.current = null;
      }

      const recorder = mediaRecorderRef.current;
      if (!recorder) {
        setIsRecording(false);
        resolve(null);
        return;
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        recorder.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);

        // Attach live transcript if captured via browser Web Speech API
        blob.transcriptText = liveTranscriptRef.current || null;
        resolve(blob);
      };

      recorder.stop();
    });
  }, []);

  return { isRecording, start, stop, error };
}
