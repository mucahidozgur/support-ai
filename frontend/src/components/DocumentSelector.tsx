"use client";

import { useEffect, useRef, useState } from "react";

import type { DocumentListItem } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface DocumentSelectorProps {
  documents: DocumentListItem[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  mode: "chat" | "agent";
}

export default function DocumentSelector({
  documents,
  selectedIds,
  onChange,
  mode,
}: DocumentSelectorProps) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Dropdown dışına tıklanınca kapanır.
  useEffect(() => {
    if (!open) return;
    function onMouseDown(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [open]);

  function toggle(id: string) {
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id]
    );
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
      >
        📄 Doküman seç ({selectedIds.length}/{documents.length})
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-10 mb-2 max-h-64 w-80 overflow-y-auto rounded-lg border border-gray-200 bg-white p-2 shadow-lg">
          <div className="mb-2 flex items-center justify-between border-b border-gray-100 pb-2 text-xs">
            <button
              onClick={() => onChange(documents.map((d) => d.id))}
              className="text-blue-600 hover:underline"
            >
              Tümünü seç
            </button>
            <button
              onClick={() => onChange([])}
              className="text-gray-500 hover:underline"
            >
              Temizle
            </button>
          </div>
          {documents.length === 0 ? (
            <p className="p-2 text-sm text-gray-500">Henüz doküman yok.</p>
          ) : (
            documents.map((doc) => (
              <label
                key={doc.id}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(doc.id)}
                  onChange={() => toggle(doc.id)}
                  className="h-4 w-4"
                />
                <span className="flex-1 truncate text-sm text-gray-800">{doc.title}</span>
                <span className="shrink-0 text-xs text-gray-400">
                  {formatDate(doc.created_at)}
                </span>
              </label>
            ))
          )}
          {mode === "agent" && (
            <p className="mt-2 border-t border-gray-100 pt-2 text-xs text-gray-500">
              Agent araçları için en az 1-2 doküman seçin
            </p>
          )}
        </div>
      )}
    </div>
  );
}
