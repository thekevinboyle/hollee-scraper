import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Oil & Gas Document Scraper",
  description: "Search and browse regulatory documents from 10 US state agencies",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">
        {children}
      </body>
    </html>
  );
}
