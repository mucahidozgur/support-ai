"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import DocumentSelector from "@/components/DocumentSelector";
import MessageBubble, { type Message } from "@/components/MessageBubble";
import { api, type DocumentListItem } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { uuid } from "@/lib/uuid";

const EXAMPLE_QUESTIONS = ["Python nedir?", "Toplantı notlarını özetle", "Yapılacakları çıkar"];

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [mode, setMode] = useState<"chat" | "agent">("chat");
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    api
      .listDocuments(100, 0)
      .then((r) => setDocuments(r.items))
      .catch(console.error);
  }, []);

  function updateMessage(id: string, patch: Partial<Message>) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }

  async function handleSend() {
    if (!input.trim() || streaming) return;
    const query = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { id: uuid(), role: "user", content: query }]);

    const assistantId = uuid();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", done: false },
    ]);
    setStreaming(true);

    try {
      const path = mode === "chat" ? "/api/ai/chat" : "/api/ai/agent";
      const body = {
        query,
        top_k: 5,
        document_ids: selectedIds.length > 0 ? selectedIds : undefined,
      };
      for await (const ev of streamSSE(path, body)) {
        const data = JSON.parse(ev.data);
        if (ev.event === "intent") {
          updateMessage(assistantId, { intent: data.intent });
        } else if (ev.event === "sources") {
          updateMessage(assistantId, { sources: data });
        } else if (ev.event === "token") {
          // content'e ekle
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + data.text } : m
            )
          );
        } else if (ev.event === "error") {
          updateMessage(assistantId, { error: data.message });
        } else if (ev.event === "done") {
          updateMessage(assistantId, { done: true });
        }
      }
    } catch (e) {
      updateMessage(assistantId, { error: (e as Error).message, done: true });
    } finally {
      setStreaming(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className="flex h-[calc(100vh-6.5rem)] flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">AI Asistan</h1>
        <div className="flex rounded-md border border-gray-300 p-1">
          <button
            onClick={() => setMode("chat")}
            className={`rounded px-3 py-1 text-sm ${
              mode === "chat"
                ? "bg-blue-600 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMode("agent")}
            className={`rounded px-3 py-1 text-sm ${
              mode === "agent"
                ? "bg-blue-600 text-white"
                : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Agent
          </button>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex min-h-full flex-col items-center justify-center gap-3 text-center">
              <span className="text-5xl">💬</span>
              <p className="text-gray-600">Dokümanlarınız hakkında soru sorun</p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    onClick={() => setInput(question)}
                    className="rounded-full border border-gray-300 px-3 py-1 text-sm text-gray-600 hover:bg-gray-100"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => <MessageBubble key={message.id} message={message} />)
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-gray-200 p-4">
          <div className="mb-2">
            <DocumentSelector
              documents={documents}
              selectedIds={selectedIds}
              onChange={setSelectedIds}
              mode={mode}
            />
          </div>
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={streaming}
              rows={2}
              placeholder="Sorunuzu yazın... (Enter: gönder, Shift+Enter: yeni satır)"
              className="flex-1 resize-none rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
            />
            <button
              onClick={() => void handleSend()}
              disabled={streaming || !input.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Gönder
            </button>
          </div>
          {mode === "agent" && selectedIds.length === 0 && (
            <p className="mt-2 text-sm text-amber-600">
              ⚠️ Özet/aksiyon/karşılaştırma için önce yukarıdan doküman seçin
            </p>
          )}
          {streaming && <p className="mt-2 text-sm text-gray-500">Yanıt yazıyor...</p>}
        </div>
      </div>

      <p className="mt-2 text-xs text-gray-400">
        Chat: dokümanlarınız hakkında soru sorun. Agent: özet/aksiyon/karşılaştırma da yapabilir.
      </p>
    </div>
  );
}
