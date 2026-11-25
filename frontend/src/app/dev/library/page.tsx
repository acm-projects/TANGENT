import { notFound } from "next/navigation";
import { DevLibrary } from "@/ui/pages/dev-library/DevLibrary";

// Dev-only: exists with the mock UI (MOCK=1) and is deleted with it.
export default function DevLibraryPage() {
  if (process.env.MOCK !== "1") notFound();
  return <DevLibrary />;
}
