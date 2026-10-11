import { Signup } from "@/ui/pages/signup/Signup";

export default async function SignupPage({ searchParams }: PageProps<"/signup">) {
  const { next } = await searchParams;
  return <Signup next={typeof next === "string" ? next : undefined} />;
}
