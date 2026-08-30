import { useCallback, useRef, useState } from "react";

const VOICE_LOCALES = {
  English: "en-IN",
  Hindi: "hi-IN",
  Tamil: "ta-IN",
  Telugu: "te-IN",
};

/** Browser SpeechSynthesis (text-to-speech): play / stop / replay. */
export function useTextToSpeech() {
  const [speakingId, setSpeakingId] = useState(null);
  const lastUtteranceRef = useRef(null);

  const speak = useCallback((text, language, id) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = VOICE_LOCALES[language] || "en-IN";
    utterance.onend = () => setSpeakingId(null);
    utterance.onerror = () => setSpeakingId(null);

    lastUtteranceRef.current = { text, language, id };
    setSpeakingId(id);
    window.speechSynthesis.speak(utterance);
  }, []);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setSpeakingId(null);
  }, []);

  const replay = useCallback(() => {
    if (lastUtteranceRef.current) {
      const { text, language, id } = lastUtteranceRef.current;
      speak(text, language, id);
    }
  }, [speak]);

  return { speak, stop, replay, speakingId };
}

/** Microphone recording -> Blob, for sending to /api/transcribe. */
export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  const start = useCallback(async () => {
    setError(null);
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
      setError("Microphone access was denied or is unavailable.");
    }
  }, []);

  const stop = useCallback(() => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder) {
        resolve(null);
        return;
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        recorder.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        resolve(blob);
      };
      recorder.stop();
    });
  }, []);

  return { isRecording, start, stop, error };
}
