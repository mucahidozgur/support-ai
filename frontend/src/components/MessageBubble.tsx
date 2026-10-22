"use client";

import { useState } from "react";

import type { ChatSource } from "@/lib/api";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string; // streaming sırasında güncellenir
  sources?: ChatSource[]; // assistant mesajları için
  intent?: string; // agent modu için
  error?: string; // hata varsa
  done?: boolean; // stream bitti mi
}

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-blue-600 px-4 py-2 text-white">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] rounded-2xl border border-gray-200 bg-white px-4 py-3">
        {message.intent && (
          <span className="mb-2 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
            intent: {message.intent}
          </span>
        )}
        <div className="text-gray-900">
          {message.content.split("\n").map((line, i) => (
            <p key={i}>{line}</p>
          ))}
        </div>
        {message.sources && message.sources.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setSourcesOpen((open) => !open)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              📎 Kaynaklar ({message.sources.length})
            </button>
            {sourcesOpen && (
              <ul className="mt-1 space-y-1 text-sm text-gray-600">
                {message.sources.map((source, i) => (
                  <li key={i}>
                    • {source.document_title} — benzerlik {source.similarity.toFixed(2)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {message.error && <p className="mt-2 text-sm text-red-600">{message.error}</p>}
        {!message.done && (
          <div className="mt-1 text-right">
            <span className="animate-pulse">▍</span>
          </div>
        )}
      </div>
    </div>
  );
}
