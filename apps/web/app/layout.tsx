import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "BNB Smart Money AI Trader",
  description: "Signal-only BNBUSDT smart money dashboard"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
