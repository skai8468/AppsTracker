import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AppsTracker",
  description: "Track job applications by link — Singapore tech & finance",
  applicationName: "AppsTracker",
  // iOS reads apple-mobile-web-app-title for the Home Screen label. Without it Safari
  // falls back to <title>, and an icon added before a rename keeps the OLD name until
  // it's removed and re-added — the name is captured once, at add time.
  appleWebApp: { title: "AppsTracker" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Required for env(safe-area-inset-*) to report real values — without it the tab bar
  // sits under the home indicator on notched iPhones.
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f9f9f9" },
    { media: "(prefers-color-scheme: dark)", color: "#1e1e20" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
