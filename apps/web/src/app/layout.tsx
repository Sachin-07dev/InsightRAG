import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InsightRAG Enterprise | Foundation",
  description:
    "The engineering foundation for private, evidence-backed knowledge and business intelligence.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
