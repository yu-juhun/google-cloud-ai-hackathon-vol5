import { useEffect, useMemo, useRef, useState } from "react";
import { PersonaSocket, Persona, AvatarTemplate } from "../ws/PersonaSocket";
import { startMicCapture, MicCapture, rmsVolume } from "../audio/micCapture";
import { createAudioPlayback, AudioPlayback } from "../audio/audioPlayback";
import "./AvatarPanel.css";

// Only the 4 voice names confirmed present in the installed google-genai
// SDK's own Live API test fixtures (live_session.py's VOICE_NAMES
// independently re-validates these server-side). The one-word
// characteristic is Google's own documented label for each voice
// (ai.google.dev/gemini-api/docs/speech-generation); gender-presentation
// is NOT something Google documents — it's third-party listening
// consensus only, shown here (clearly caveated) so it's easier to pair a
// voice with a generated avatar's appearance.
const VOICE_OPTIONS = [
  { value: "", label: "おまかせ（既定の声）" },
  { value: "Puck", label: "Puck（アップビート・男性的とされる）" },
  { value: "Charon", label: "Charon（説明的・男性的とされる）" },
  { value: "Kore", label: "Kore（しっかりした・女性的とされる）" },
  { value: "Leda", label: "Leda（若々しい・女性的とされる）" },
];

const GENDER_LABELS: Record<string, string> = { male: "男性", female: "女性" };

export function AvatarPanel({ socket }: { socket: PersonaSocket }) {
  const [mouthOpen, setMouthOpen] = useState(false);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [capture, setCapture] = useState<MicCapture | null>(null);
  const [baseAvatarImage, setBaseAvatarImage] = useState<string | null>(null);
  const [baseAvatarImageOpen, setBaseAvatarImageOpen] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [templates, setTemplates] = useState<AvatarTemplate[]>([]);
  const [gender, setGender] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const playbackRef = useRef<AudioPlayback | null>(null);
  const captureRef = useRef<MicCapture | null>(null);
  const resultReceivedRef = useRef(false);

  useEffect(() => {
    socket.onPersonaResult = (result) => {
      resultReceivedRef.current = true;
      setPersona(result);
      setErrorMessage(null);
    };
    socket.onAvatarBaseImage = (imageBase64, openMouthImageBase64) => {
      setBaseAvatarImage(imageBase64);
      setBaseAvatarImageOpen(openMouthImageBase64);
      setErrorMessage(null);
    };
    socket.onAvatarError = (message) => setErrorMessage(`アバター写真の処理に失敗しました: ${message}`);
    socket.onFinishError = (message) => setErrorMessage(`結果の生成に失敗しました: ${message}`);
    socket.onStartError = (message) => setErrorMessage(`会話の開始に失敗しました: ${message}`);
    socket.onAvatarTemplates = (received) => setTemplates(received);
    socket.onDisconnected = () => {
      // A close after persona_result already arrived is the normal end
      // of the flow, not a failure — only report it if the conversation
      // was cut off before ever finishing.
      if (!resultReceivedRef.current) {
        setErrorMessage("接続が予期せず切断されました。もう一度お試しください。");
      }
    };
    socket.onAudioChunk = (chunk) => {
      if (!playbackRef.current) {
        playbackRef.current = createAudioPlayback();
      }
      playbackRef.current.playChunk(chunk);
      setMouthOpen(rmsVolume(chunk) > 0.02);
    };

    // Connect eagerly on mount so the real avatar_templates catalog has
    // already arrived by the time the user opens the style picker or
    // selects a photo, instead of the dropdown being empty until whichever
    // action (話しかける / photo upload) happens to connect first.
    // Promise.resolve(...) tolerates test doubles whose mocked connect()
    // doesn't return a real promise.
    Promise.resolve(socket.connect()).catch(() => {
      // A failed eager connect surfaces again through onStartError/
      // onDisconnected when the user actually tries to do something —
      // no need to show an error before they've taken any action.
    });

    return () => {
      playbackRef.current?.stop();
      playbackRef.current = null;
      // Without this, navigating away mid-conversation (unmounting
      // without ever clicking 完了) leaves the mic stream open
      // indefinitely — the browser's recording indicator stays on.
      captureRef.current?.stop();
      captureRef.current = null;
    };
  }, [socket]);

  const handleStart = async () => {
    try {
      await socket.connect(voiceName || undefined);
      const mic = await startMicCapture(
        (chunk) => socket.sendAudioChunk(chunk),
        () => {},
      );
      setCapture(mic);
      captureRef.current = mic;
    } catch (e) {
      // A rejected connect() or a denied mic permission would otherwise
      // be an unhandled promise rejection — the button would just do
      // nothing with no feedback at all.
      setErrorMessage(`会話の開始に失敗しました: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleFinish = () => {
    socket.sendFinish();
    capture?.stop();
    captureRef.current = null;
  };

  const handlePhotoChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const buffer = await file.arrayBuffer();
      await socket.connect(voiceName || undefined);
      socket.sendAvatarPhoto(buffer, file.type, templateId || undefined);
    } catch (e) {
      setErrorMessage(`アバター写真の処理に失敗しました: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const availableGenders = useMemo(
    () => Array.from(new Set(templates.map((t) => t.gender).filter(Boolean))),
    [templates],
  );
  const stylesForGender = useMemo(
    () => templates.filter((t) => !gender || t.gender === gender),
    [templates, gender],
  );

  const handleGenderChange = (value: string) => {
    setGender(value);
    // The previously selected style may not exist for the newly chosen
    // gender (most styles aren't offered for both) — clear it rather
    // than silently keep sending a template_id that doesn't match.
    setTemplateId("");
  };

  const closedSrc = persona?.avatar_image
    ? `data:image/png;base64,${persona.avatar_image}`
    : baseAvatarImage
      ? `data:image/png;base64,${baseAvatarImage}`
      : "/avatar-default-closed.png";

  const openSrc = persona?.avatar_image_open
    ? `data:image/png;base64,${persona.avatar_image_open}`
    : baseAvatarImageOpen
      ? `data:image/png;base64,${baseAvatarImageOpen}`
      : "/avatar-default-open.png";

  return (
    <div className="avatar-panel">
      <header className="avatar-panel__header">
        <h1 className="avatar-panel__title">ペルソナ・インテイクエージェント</h1>
      </header>

      <section className="avatar-panel__avatar-card">
        <img
          className="avatar-panel__avatar-image"
          src={mouthOpen ? openSrc : closedSrc}
          alt="アバター"
          width={200}
          height={200}
        />
        <label className="avatar-panel__upload">
          <span>顔写真をアップロード</span>
          <input type="file" accept="image/*" onChange={handlePhotoChange} />
        </label>
      </section>

      <section className="avatar-panel__options">
        <label className="avatar-panel__option">
          <span>性別</span>
          <select value={gender} onChange={(e) => handleGenderChange(e.target.value)}>
            <option value="">おまかせ（既定）</option>
            {availableGenders.map((g) => (
              <option key={g} value={g}>
                {GENDER_LABELS[g] ?? g}
              </option>
            ))}
          </select>
        </label>
        <label className="avatar-panel__option">
          <span>アバターのスタイル</span>
          <select value={templateId} onChange={(e) => setTemplateId(e.target.value)} disabled={templates.length === 0}>
            <option value="">おまかせ（既定）</option>
            {stylesForGender.map((t) => (
              <option key={t.id} value={t.id}>
                {t.category} - {t.title}
              </option>
            ))}
          </select>
        </label>
        <label className="avatar-panel__option">
          <span>声を選ぶ</span>
          <select value={voiceName} onChange={(e) => setVoiceName(e.target.value)}>
            {VOICE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="avatar-panel__controls">
        <button className="avatar-panel__button avatar-panel__button--primary" onClick={handleStart}>
          話しかける
        </button>
        <button className="avatar-panel__button avatar-panel__button--secondary" onClick={handleFinish}>
          完了
        </button>
      </section>

      {errorMessage && (
        <p className="avatar-panel__error" role="alert">
          {errorMessage}
        </p>
      )}

      {persona && (
        <section className="avatar-panel__result">
          <p className="avatar-panel__summary">{persona.raw_summary}</p>
          <ul className="avatar-panel__attributes">
            {persona.attributes.map((attr, i) => (
              <li key={i} className="avatar-panel__attribute">
                <span className="avatar-panel__attribute-category">{attr.category}</span>
                <span className="avatar-panel__attribute-description">{attr.description}</span>
                {attr.inferred_keywords.length > 0 && (
                  <span className="avatar-panel__attribute-keywords">{attr.inferred_keywords.join(", ")}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
