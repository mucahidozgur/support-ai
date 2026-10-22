import { formatDate } from "@/lib/format";
import type { DocumentListItem } from "@/lib/api";

interface DocumentCardProps {
  document: DocumentListItem;
  onDelete: (id: string) => void;
  onIndex: (id: string) => void;
}

export default function DocumentCard({ document, onDelete, onIndex }: DocumentCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-4">
        <h3 className="text-lg font-semibold">{document.title}</h3>
        <span className="shrink-0 text-sm text-gray-500">
          {formatDate(document.created_at)}
        </span>
      </div>
      <p className="mb-3 line-clamp-2 text-gray-700">{document.content_preview}</p>
      <div className="flex items-center gap-4">
        <button
          onClick={() => onIndex(document.id)}
          className="rounded-md border border-blue-600 px-3 py-1 text-sm text-blue-600 hover:bg-blue-50"
        >
          Index
        </button>
        <button
          onClick={() => onDelete(document.id)}
          className="text-sm text-red-600 hover:underline"
        >
          Sil
        </button>
      </div>
    </div>
  );
}
