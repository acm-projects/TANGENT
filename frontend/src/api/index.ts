/**
 * The one entry point features import from: `import { api } from "@/api"`.
 *
 * Each endpoint group is a factory taking an ApiClient, so tests can build one
 * against a fake adapter instead of mocking modules. This file wires the
 * factories to the app's shared client exactly once.
 *
 * Files INSIDE api/ import each other by relative path, never through this
 * barrel -- that would be a cycle.
 */

import { createAuthApi } from "./endpoints/auth";
import { createNodesApi } from "./endpoints/nodes";
import { createTreesApi } from "./endpoints/trees";
import { apiClient } from "./session";

export const api = {
  auth: createAuthApi(apiClient),
  nodes: createNodesApi(apiClient),
  trees: createTreesApi(apiClient),
};

export type Api = typeof api;

// Streaming is not request/response, so it is not part of `api`.
export { streamMessage } from "./stream";
export { apiClient, getAccessToken, setAccessToken } from "./session";
export type * from "./types";
