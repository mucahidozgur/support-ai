"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import DocumentCard from "@/components/DocumentCard";
import NewDocumentModal from "@/components/NewDocumentModal";
import { api, type Document, type DocumentListItem } from "@/lib/api";
import { useAuth } from "@/lib/store";

export default function DashboardPage() {
  const router = useRouter();
  const { user, loading: authLoading, checkAuth } = useAuth();
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/");
    }
  }, [authLoading, user, router]);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const res = await api.listDocuments();
      setDocuments(res.items);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) {
      void refresh();
    }
  }, [user, refresh]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3000);
      return () => clearTimeout(t);
    }
  }, [toast]);

  // Oluştur → otomatik index'le → listeyi yenile → toast
  async function handleCreated(doc: Document) {
    setModalOpen(false);
    try {
      await api.indexDocument(doc.id);
      await refresh();
      setToast("Doküman oluşturuldu ve indexlendi");
    } catch {
      await refresh();
      setToast("Doküman oluşturuldu ancak indexlenemedi");
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Bu dokümanı silmek istediğinize emin misiniz?")) {
      return;
    }
    try {
      await api.deleteDocument(id);
      setToast("Doküman silindi");
      await refresh();
    } catch (e) {
      setToast(`Silinemedi: ${(e as Error).message}`);
    }
  }

  async function handleIndex(id: string) {
    try {
      await api.indexDocument(id);
      setToast("Doküman indexlendi");
    } catch (e) {
      setToast(`Indexlenemedi: ${(e as Error).message}`);
    }
  }

  if (authLoading || !user) {
    return null;
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dokümanlar</h1>
        <button
          onClick={() => setModalOpen(true)}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Yeni Doküman
        </button>
      </div>

      {loading ? (
        <p className="text-gray-500">Yükleniyor...</p>
      ) : error ? (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      ) : documents.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <p className="text-gray-500">
            Henüz dokümanınız yok. İlk dokümanınızı oluşturun.
          </p>
          <button
            onClick={() => setModalOpen(true)}
            className="rounded-md bg-blue-600 px-6 py-3 text-base font-medium text-white hover:bg-blue-700"
          >
            Yeni Doküman
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onDelete={handleDelete}
              onIndex={handleIndex}
            />
          ))}
        </div>
      )}

      {modalOpen && (
        <NewDocumentModal onClose={() => setModalOpen(false)} onCreated={handleCreated} />
      )}

      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg bg-gray-900 px-4 py-2 text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
