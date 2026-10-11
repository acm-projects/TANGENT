import { Login } from "@/ui/pages/login/Login";

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams;
  return <Login next={typeof next === "string" ? next : undefined} />;
}
