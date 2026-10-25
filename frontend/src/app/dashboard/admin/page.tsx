"use client";

import { useEffect, useState } from "react";

import {
  api,
  type AnalyticsStats,
  type RecentQueryItem,
  type TopQueryItem,
} from "@/lib/api";

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function FaithfulnessBar({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-xs text-gray-400">—</span>;
  }
  const width = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const color = value >= 0.7 ? "bg-green-500" : value >= 0.5 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-200">
        <div className={`h-full ${color}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-xs text-gray-600">{value.toFixed(2)}</span>
    </div>
  );
}

function FeedbackIcon({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-xs text-gray-400">—</span>;
  }
  return value === 1 ? (
    <span className="text-green-600" title="Olumlu">
      👍
    </span>
  ) : (
    <span className="text-red-600" title="Olumsuz">
      👎
    </span>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<AnalyticsStats | null>(null);
  const [recent, setRecent] = useState<RecentQueryItem[]>([]);
  const [top, setTop] = useState<TopQueryItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [statsRes, recentRes, topRes] = await Promise.all([
          api.getAnalyticsStats(),
          api.getRecentQueries(20),
          api.getTopQueries(),
        ]);
        setStats(statsRes);
        setRecent(recentRes);
        setTop(topRes);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  if (error) {
    return (
      <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">
        Analitik verisi alınamadı: {error}
      </div>
    );
  }
  if (!stats) {
    return <p className="text-gray-500">Yükleniyor...</p>;
  }

  const kpis = [
    { label: "Toplam Sorgu", value: stats.total_queries.toLocaleString("tr-TR") },
    { label: "Ort. Faithfulness", value: stats.avg_faithfulness.toFixed(2) },
    { label: "Yetersiz Context", value: formatPercent(stats.insufficient_context_rate) },
    {
      label: "Olumlu Geri Bildirim",
      value: `${stats.feedback_positive} / ${
        stats.feedback_positive + stats.feedback_negative
      }`,
    },
  ];

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Analytics</h1>

      {/* KPI kartları */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
              {kpi.label}
            </p>
            <p className="mt-1 text-2xl font-bold text-gray-900">{kpi.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Son 20 sorgu */}
        <div className="lg:col-span-2 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-4 text-lg font-semibold">Son Sorgular</h2>
          {recent.length === 0 ? (
            <p className="text-sm text-gray-500">Henüz sorgu kaydı yok.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs uppercase text-gray-500">
                  <th className="pb-2 pr-4 font-medium">Sorgu</th>
                  <th className="pb-2 pr-4 font-medium">Faithfulness</th>
                  <th className="pb-2 pr-4 font-medium">Gecikme</th>
                  <th className="pb-2 font-medium">Feedback</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((item) => (
                  <tr key={item.id} className="border-b border-gray-100 last:border-0">
                    <td className="max-w-[280px] truncate py-2 pr-4 text-gray-800" title={item.query}>
                      {item.query}
                    </td>
                    <td className="py-2 pr-4">
                      <FaithfulnessBar value={item.faithfulness} />
                    </td>
                    <td className="py-2 pr-4 text-xs text-gray-600">
                      {item.latency_ms === null ? "—" : `${item.latency_ms} ms`}
                    </td>
                    <td className="py-2">
                      <FeedbackIcon value={item.feedback} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Top 10 sorgu */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-4 text-lg font-semibold">En Çok Sorulanlar</h2>
          {top.length === 0 ? (
            <p className="text-sm text-gray-500">Henüz sorgu kaydı yok.</p>
          ) : (
            <ol className="space-y-2">
              {top.map((item, index) => (
                <li key={item.query} className="flex items-start gap-3 text-sm">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-gray-800" title={item.query}>
                      {item.query}
                    </p>
                    <p className="text-xs text-gray-500">{item.count} sorgu</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
