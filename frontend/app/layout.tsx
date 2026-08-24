import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JobTrack SG",
  description: "Fresh-grad & intern job tracker for Singapore tech & finance",
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
