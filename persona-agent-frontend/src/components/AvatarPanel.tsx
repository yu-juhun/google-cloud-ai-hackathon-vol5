import { useEffect, useRef, useState } from "react";
import { PersonaSocket, Persona } from "../ws/PersonaSocket";
import { startMicCapture, MicCapture } from "../audio/micCapture";
import { createAudioPlayback, AudioPlayback } from "../audio/audioPlayback";

export function AvatarPanel({ socket }: { socket: PersonaSocket }) {
  const [mouthOpen, setMouthOpen] = useState(false);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [capture, setCapture] = useState<MicCapture | null>(null);
  const [baseAvatarImage, setBaseAvatarImage] = useState<string | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);

  useEffect(() => {
    socket.onPersonaResult = (result) => setPersona(result);
    socket.onAvatarBaseImage = (imageBase64) => setBaseAvatarImage(imageBase64);
    socket.onAudioChunk = (chunk) => {
      if (!playbackRef.current) {
        playbackRef.current = createAudioPlayback();
      }
      playbackRef.current.playChunk(chunk);

      const view = new Int16Array(chunk);
      let sumSquares = 0;
      for (let i = 0; i < view.length; i++) sumSquares += (view[i] / 0x7fff) ** 2;
      const volume = Math.sqrt(sumSquares / view.length);
      setMouthOpen(volume > 0.02);
    };

    return () => {
      playbackRef.current?.stop();
      playbackRef.current = null;
    };
  }, [socket]);

  const handleStart = async () => {
    await socket.connect();
    const mic = await startMicCapture(
      (chunk) => socket.sendAudioChunk(chunk),
      () => {},
    );
    setCapture(mic);
  };

  const handleFinish = () => {
    socket.sendFinish();
    capture?.stop();
  };

  const handlePhotoChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const buffer = await file.arrayBuffer();
    await socket.connect();
    socket.sendAvatarPhoto(buffer, file.type);
  };

  const baseSrc = persona?.avatar_image
    ? `data:image/png;base64,${persona.avatar_image}`
    : baseAvatarImage
      ? `data:image/png;base64,${baseAvatarImage}`
      : "/avatar-mouth-closed.svg";

  return (
    <div>
      <label>
        顔写真をアップロード
        <input type="file" accept="image/*" onChange={handlePhotoChange} />
      </label>
      <img src={mouthOpen ? "/avatar-mouth-open.svg" : baseSrc} alt="アバター" width={200} height={200} />
      <button onClick={handleStart}>話しかける</button>
      <button onClick={handleFinish}>完了</button>
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
