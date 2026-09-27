import { useEffect, useRef, useState } from "react";
import { PersonaSocket, Persona } from "../ws/PersonaSocket";
import { startMicCapture, MicCapture, rmsVolume } from "../audio/micCapture";
import { createAudioPlayback, AudioPlayback } from "../audio/audioPlayback";

export function AvatarPanel({ socket }: { socket: PersonaSocket }) {
  const [mouthOpen, setMouthOpen] = useState(false);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [capture, setCapture] = useState<MicCapture | null>(null);
  const [baseAvatarImage, setBaseAvatarImage] = useState<string | null>(null);
  const [baseAvatarImageOpen, setBaseAvatarImageOpen] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);

  useEffect(() => {
    socket.onPersonaResult = (result) => {
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
    socket.onAudioChunk = (chunk) => {
      if (!playbackRef.current) {
        playbackRef.current = createAudioPlayback();
      }
      playbackRef.current.playChunk(chunk);
      setMouthOpen(rmsVolume(chunk) > 0.02);
    };

    return () => {
      playbackRef.current?.stop();
      playbackRef.current = null;
    };
  }, [socket]);

  const handleStart = async () => {
    try {
      await socket.connect();
      const mic = await startMicCapture(
        (chunk) => socket.sendAudioChunk(chunk),
        () => {},
      );
      setCapture(mic);
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
  };

  const handlePhotoChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const buffer = await file.arrayBuffer();
      await socket.connect();
      socket.sendAvatarPhoto(buffer, file.type);
    } catch (e) {
      setErrorMessage(`アバター写真の処理に失敗しました: ${e instanceof Error ? e.message : String(e)}`);
    }
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
    <div>
      <label>
        顔写真をアップロード
        <input type="file" accept="image/*" onChange={handlePhotoChange} />
      </label>
      <img src={mouthOpen ? openSrc : closedSrc} alt="アバター" width={200} height={200} />
      <button onClick={handleStart}>話しかける</button>
      <button onClick={handleFinish}>完了</button>
      {errorMessage && <p role="alert">{errorMessage}</p>}
      {persona && (
        <div>
          <p>{persona.raw_summary}</p>
          <ul>
            {persona.attributes.map((attr, i) => (
              <li key={i}>
                {attr.category}: {attr.description} ({attr.inferred_keywords.join(", ")})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
