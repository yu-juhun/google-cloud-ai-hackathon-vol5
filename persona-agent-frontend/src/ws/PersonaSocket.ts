export interface PersonaAttribute {
  domain: "mobility" | "dietary" | "purpose" | "companions" | "language" | "background" | "other";
  category: string;
  description: string;
  rank: number;
  confidence: "high" | "medium" | "low";
  inferred_keywords: string[];
}

export interface Persona {
  persona_id: string;
  raw_summary: string;
  attributes: PersonaAttribute[];
  avatar_image: string | null;
}

export class PersonaSocket {
  private ws: WebSocket | null = null;
  onPersonaResult: ((persona: Persona) => void) | null = null;
  onAudioChunk: ((chunk: ArrayBuffer) => void) | null = null;
  onAvatarBaseImage: ((imageBase64: string) => void) | null = null;

  constructor(private url: string) {}

  /** Resolves once the socket has actually reached OPEN. Callers that need
   * to start sending immediately after connecting (e.g. mic capture) must
   * await this — sending while the socket is still CONNECTING throws
   * InvalidStateError, silently dropping audio chunks sent too early. */
  connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.url);
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = (event) => reject(event);
      ws.onmessage = (event: { data: string }) => {
        const message = JSON.parse(event.data);
        if (message.type === "persona_result") {
          this.onPersonaResult?.(message.data as Persona);
        } else if (message.type === "audio_chunk") {
          const binary = atob(message.data as string);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          this.onAudioChunk?.(bytes.buffer);
        } else if (message.type === "avatar_base_image") {
          this.onAvatarBaseImage?.(message.data as string);
        }
      };
    });
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const base64 = btoa(String.fromCharCode(...new Uint8Array(chunk)));
    this.ws.send(JSON.stringify({ type: "audio_chunk", data: base64 }));
  }

  sendAvatarPhoto(photo: ArrayBuffer, contentType: string): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    const base64 = btoa(String.fromCharCode(...new Uint8Array(photo)));
    this.ws.send(JSON.stringify({ type: "avatar_photo", data: base64, content_type: contentType }));
  }

  sendFinish(): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "finish" }));
  }

  close(): void {
    this.ws?.close();
  }
}
