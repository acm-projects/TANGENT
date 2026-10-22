import type { Metadata } from "next";
import { Aleo, Outfit } from "next/font/google";
import localFont from "next/font/local";
import "katex/dist/katex.min.css";
import { lightingScript } from "@/ui/library/tokens/lighting";
import "./globals.css";

const heading = Aleo({ weight: "400", subsets: ["latin"], variable: "--font-heading" });
const content = Outfit({ subsets: ["latin"], variable: "--font-content" });

/* next/font/google doesn't carry Material Symbols, so it comes from the
 * @material-symbols/font-400 package. "block" hides the ligature names
 * ("home") until the glyphs load. Fill is set in Icon.css. */
const materialSymbols = localFont({
  src: "../../node_modules/@material-symbols/font-400/material-symbols-rounded.woff2",
  display: "block",
  variable: "--font-symbols",
});

export const metadata: Metadata = {
  title: "Tangent",
  description: "A research board where every conversation can branch.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${heading.variable} ${content.variable} ${materialSymbols.variable}`}
      // lightingScript marks <html>'s lighting before React hydrates
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: lightingScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
