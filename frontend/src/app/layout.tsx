import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Support AI",
  description: "Enterprise RAG assistant for customer support teams",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
