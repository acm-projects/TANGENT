import { useRouter } from "next/navigation";
import { api, setAccessToken } from "@/api";
import { loginPath } from "@/ui/features/auth/paths";

/** Ends the session and goes to login. A failed logout still signs out here: the token is dropped either way. */
export function useSignOut() {
  const router = useRouter();
  return async () => {
    await api.auth.logout().catch(() => {});
    setAccessToken(null);
    router.push(loginPath());
  };
}
