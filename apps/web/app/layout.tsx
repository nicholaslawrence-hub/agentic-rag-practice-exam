import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MCB Tutor — UC Berkeley",
  description: "Adaptive Socratic tutor for UC Berkeley Molecular & Cell Biology courses",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-white text-slate-900 antialiased">{children}</body>
    </html>
  );
}
