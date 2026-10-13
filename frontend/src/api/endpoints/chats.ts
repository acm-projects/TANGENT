import type { ApiClient } from "../client";
import type { AvailableModel } from "../types";

/** GET /models -- the LLMs the server will call, for the model picker. */
export function createChatsApi({ http }: ApiClient) {
  return {
    models: () => http.get<AvailableModel[]>("/models").then((r) => r.data),
  };
}

export type ChatsApi = ReturnType<typeof createChatsApi>;
