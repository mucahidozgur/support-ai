"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import LoginForm from "@/components/LoginForm";
import { useAuth } from "@/lib/store";

export default function Home() {
  const router = useRouter();
  const { user, loading, checkAuth } = useAuth();

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (user) {
      router.push("/dashboard");
    }
  }, [user, router]);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">Yükleniyor...</p>
      </main>
    );
  }
  if (!user) {
    return <LoginForm />;
  }
  // Yönlendirme efekti çalışana kadar boş render.
  return null;
}
