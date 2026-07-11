import type { ReactNode } from "react";

export const metadata = {
  title: "Occasion",
  description: "Plan any event with an autonomous agent team.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
