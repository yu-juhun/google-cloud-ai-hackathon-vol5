export interface PersonaAttribute {
  category: string;
  description: string;
  priority: "high" | "medium" | "low";
  confidence: "high" | "medium" | "low";
  inferred_keywords: string[];
}

export interface Persona {
  persona_id: string;
  raw_summary: string;
  attributes: PersonaAttribute[];
}

export class PersonaSocket {
  private ws: WebSocket | null = null;
  onPersonaResult: ((persona: Persona) => void) | null = null;
  onAudioChunk: ((chunk: ArrayBuffer) => void) | null = null;

  constructor(private url: string) {}

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event: { data: string }) => {
      const message = JSON.parse(event.data);
      if (message.type === "persona_result") {
        this.onPersonaResult?.(message.data as Persona);
      } else if (message.type === "audio_chunk") {
        const binary = atob(message.data as string);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        this.onAudioChunk?.(bytes.buffer);
      }
    };
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    const base64 = btoa(String.fromCharCode(...new Uint8Array(chunk)));
    this.ws?.send(JSON.stringify({ type: "audio_chunk", data: base64 }));
  }

  sendFinish(): void {
    this.ws?.send(JSON.stringify({ type: "finish" }));
  }

  close(): void {
    this.ws?.close();
  }
}
