// SSE client: backend endpoint'lerimiz POST olduğu için native EventSource
// (yalnızca GET) kullanılamaz; fetch + ReadableStream ile parse ederiz.

import { API_URL, clearToken, getToken } from "./api";

export interface SSEEvent {
  event: string;
  data: string;
}

export async function* streamSSE(
  path: string,
  body: object,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const token = getToken();
  if (!token) {
    if (typeof window !== "undefined") window.location.href = "/";
    throw new Error("Oturum bulunamadı");
  }
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/";
    }
    throw new Error("Oturum süresi doldu, tekrar giriş yapın");
  }
  if (!res.ok || !res.body) {
    throw new Error(`SSE error: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    // sse-starlette satır sonlarını \r\n gönderir; normalize edilmezse
    // \n\n ayracı \r\n\r\n içinde hiç bulunamaz ve event yield edilmez.
    buffer = buffer.replace(/\r\n/g, "\n");
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let eventName = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        const l = line.replace(/\r$/, "");
        if (l.startsWith("event: ")) eventName = l.slice(7);
        else if (l.startsWith("data: ")) data += l.slice(6);
      }
      if (data) yield { event: eventName, data };
    }
  }
}
