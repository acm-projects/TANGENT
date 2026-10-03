import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TANGENT",
  description: "TANGENT",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
