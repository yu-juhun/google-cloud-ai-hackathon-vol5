export interface PersonaAttribute {
  domain: "mobility" | "dietary" | "purpose" | "companions" | "language" | "background" | "other";
  category: string;
  description: string;
  rank: number;
  confidence: "high" | "medium" | "low";
  inferred_keywords: string[];
}

export interface AvatarTemplate {
  id: string;
  title: string;
  category: string;
  gender: string;
}

export interface Persona {
  persona_id: string;
  raw_summary: string;
  attributes: PersonaAttribute[];
  schema_version: string;
  avatar_image: string | null;
  avatar_image_open: string | null;
}

/** Converts an ArrayBuffer to base64 without spreading it into
 * String.fromCharCode's argument list — spreading a large Uint8Array
 * (e.g. a multi-hundred-KB/multi-MB photo) exceeds the JS engine's
 * function-argument limit and throws, silently failing with no visible
 * error since callers don't wrap this in a try/catch. Chunking keeps
 * every fromCharCode call well under that limit. */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const CHUNK_SIZE = 8192;
  let binary = "";
  for (let i = 0; i < bytes.length; i += CHUNK_SIZE) {
    const chunk = bytes.subarray(i, i + CHUNK_SIZE);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

export class PersonaSocket {
  private ws: WebSocket | null = null;
  private connecting: Promise<void> | null = null;
  onPersonaResult: ((persona: Persona) => void) | null = null;
  onAudioChunk: ((chunk: ArrayBuffer) => void) | null = null;
  onAvatarBaseImage: ((imageBase64: string, openMouthImageBase64: string) => void) | null = null;
  onAvatarError: ((message: string) => void) | null = null;
  onFinishError: ((message: string) => void) | null = null;
  onStartError: ((message: string) => void) | null = null;
  /** Fires when the connection closes for any reason other than the
   * client itself never having connected — including an unexpected
   * drop (network loss, server restart) that none of the other
   * callbacks would otherwise report. */
  onDisconnected: ((event: CloseEvent) => void) | null = null;
  /** Fires once per connection with the real, currently-available YouCam
   * avatar template catalog (see persona-agent-backend's
   * youcam_client.list_avatar_templates) — never a hardcoded guess. */
  onAvatarTemplates: ((templates: AvatarTemplate[]) => void) | null = null;

  constructor(private url: string) {}

  /** Resolves once the socket has actually reached OPEN. Callers that need
   * to start sending immediately after connecting (e.g. mic capture) must
   * await this — sending while the socket is still CONNECTING throws
   * InvalidStateError, silently dropping audio chunks sent too early.
   *
   * voiceName, if given, is only used on the FIRST call that actually
   * opens the socket (voice must be chosen before the Live session
   * exists server-side, so it travels as a connect-time query param —
   * a later connect() call on an already-open/connecting socket is a
   * no-op and can't retroactively change it). */
  connect(voiceName?: string): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) return Promise.resolve();
    // Without this, a second connect() while the first is still
    // CONNECTING (e.g. clicking 話しかける then immediately picking a
    // photo) would create a whole second WebSocket, orphaning the first
    // one mid-handshake instead of reusing it.
    if (this.connecting) return this.connecting;
    this.connecting = new Promise((resolve, reject) => {
      const url = voiceName ? `${this.url}?voice=${encodeURIComponent(voiceName)}` : this.url;
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => {
        this.connecting = null;
        resolve();
      };
      ws.onerror = (event) => {
        this.connecting = null;
        reject(event);
      };
      ws.onclose = (event) => this.onDisconnected?.(event);
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
          this.onAvatarBaseImage?.(message.data as string, message.open_mouth_data as string);
        } else if (message.type === "avatar_error") {
          this.onAvatarError?.(message.message as string);
        } else if (message.type === "finish_error") {
          this.onFinishError?.(message.message as string);
        } else if (message.type === "start_error") {
          this.onStartError?.(message.message as string);
        } else if (message.type === "avatar_templates") {
          this.onAvatarTemplates?.(message.data as AvatarTemplate[]);
        }
      };
    });
    return this.connecting;
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "audio_chunk", data: arrayBufferToBase64(chunk) }));
  }

  sendAvatarPhoto(photo: ArrayBuffer, contentType: string, templateId?: string): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(
      JSON.stringify({
        type: "avatar_photo",
        data: arrayBufferToBase64(photo),
        content_type: contentType,
        ...(templateId ? { template_id: templateId } : {}),
      }),
    );
  }

  sendFinish(): void {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "finish" }));
  }

  close(): void {
    this.ws?.close();
  }
}
