"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, checkAuth, logout } = useAuth();
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    checkAuth().finally(() => setChecked(true));
  }, [checkAuth]);

  useEffect(() => {
    if (checked && !user) {
      router.push("/");
    }
  }, [checked, user, router]);

  if (loading || !checked) {
    return <div className="p-8">Yükleniyor...</div>;
  }
  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <span className="text-lg font-bold">Support AI</span>
        <div className="flex items-center gap-4">
          {user && <span className="text-sm text-gray-600">{user.username}</span>}
          <button
            onClick={logout}
            className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
          >
            Çıkış
          </button>
        </div>
      </header>
      <div className="flex flex-1">
        <aside className="w-[200px] shrink-0 border-r border-gray-200 bg-white p-4">
          <nav className="flex flex-col gap-1 text-sm">
            <Link
              href="/dashboard"
              className="rounded-md px-3 py-2 text-gray-700 hover:bg-gray-100"
            >
              Dokümanlar
            </Link>
            <Link
              href="/dashboard/assistant"
              className="rounded-md px-3 py-2 text-gray-700 hover:bg-gray-100"
            >
              AI Asistan
            </Link>
          </nav>
        </aside>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
