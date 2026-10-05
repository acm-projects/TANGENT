import type { Metadata } from "next";
import { Bungee, Roboto } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

const bungee = Bungee({ weight: "400", subsets: ["latin"], variable: "--font-bungee" });
const roboto = Roboto({ subsets: ["latin"], variable: "--font-roboto" });

/* next/font/google doesn't carry Material Symbols, so it comes from the
 * @material-symbols/font-400 package. "block" hides the ligature names
 * ("home") until the glyphs load. Fill is set in Icon.css. */
const materialSymbols = localFont({
  src: "../../node_modules/@material-symbols/font-400/material-symbols-rounded.woff2",
  display: "block",
  variable: "--font-material-symbols",
});

export const metadata: Metadata = {
  title: "TANGENT",
  description: "TANGENT",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="dark"
      className={`${bungee.variable} ${roboto.variable} ${materialSymbols.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
