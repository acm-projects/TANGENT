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

import { createAgentApi } from "./endpoints/agent";
import { createAuthApi } from "./endpoints/auth";
import { createChatsApi } from "./endpoints/chats";
import { createDebatesApi } from "./endpoints/debates";
import { createNodesApi } from "./endpoints/nodes";
import { createProjectsApi } from "./endpoints/projects";
import { createSharesApi } from "./endpoints/shares";
import { createSourcesApi } from "./endpoints/sources";
import { createTreesApi } from "./endpoints/trees";
import { createWorkspacesApi } from "./endpoints/workspaces";
import { apiClient } from "./session";

export const api = {
  agent: createAgentApi(apiClient),
  auth: createAuthApi(apiClient),
  chats: createChatsApi(apiClient),
  debates: createDebatesApi(apiClient),
  nodes: createNodesApi(apiClient),
  projects: createProjectsApi(apiClient),
  shares: createSharesApi(apiClient),
  sources: createSourcesApi(apiClient),
  trees: createTreesApi(apiClient),
  workspaces: createWorkspacesApi(apiClient),
};

export type Api = typeof api;

// Streaming is not request/response, so it is not part of `api`.
export { DebateGoneError, streamDebate, streamMessage } from "./stream";
export type { DebateStreamEvent } from "./stream";
export { apiErrorMessage, apiErrorStatus, CopyExistsError, forkedProjectIdOf } from "./errors";
export { apiClient, getAccessToken, setAccessToken, takeTokenFromUrl } from "./session";
export type * from "./types";
