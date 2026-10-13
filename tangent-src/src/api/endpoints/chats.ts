import type { ApiClient } from "../client";
import type { AvailableModel } from "../types";

/** Standalone model endpoints used by the streaming demo. */
export function createChatsApi({ http }: ApiClient) {
  return {
    models: () => http.get<AvailableModel[]>("/models").then((r) => r.data),
  };
}

export type ChatsApi = ReturnType<typeof createChatsApi>;
