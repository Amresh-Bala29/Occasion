import type { ReactNode } from "react";
import { Hanken_Grotesk, JetBrains_Mono, Newsreader } from "next/font/google";

import "./globals.css";

const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-newsreader" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });

export const metadata = {
  title: "Occasion",
  description: "Plan any event with an autonomous agent team.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
