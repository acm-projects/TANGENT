(globalThis["TURBOPACK"] || (globalThis["TURBOPACK"] = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/frontend/src/api/client.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createApiClient",
    ()=>createApiClient
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/axios/lib/axios.js [app-client] (ecmascript)");
;
function createApiClient(opts) {
    const { baseURL, auth, adapter } = opts;
    const http = __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].create({
        baseURL,
        adapter
    });
    // Bare instance (no interceptors) so a failing refresh can't recurse into itself.
    const bare = __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].create({
        baseURL,
        withCredentials: true,
        adapter
    });
    let inflight = null;
    const refresh = ()=>{
        inflight ??= bare.post("/auth/refresh").then((r)=>{
            auth.setAccessToken(r.data.access_token);
            return r.data.access_token;
        }).catch((e)=>{
            auth.setAccessToken(null);
            auth.onAuthFailure();
            throw e;
        }).finally(()=>{
            inflight = null;
        });
        return inflight;
    };
    http.interceptors.request.use({
        "createApiClient.use": (cfg)=>{
            const token = auth.getAccessToken();
            if (token) cfg.headers.Authorization = `Bearer ${token}`;
            return cfg;
        }
    }["createApiClient.use"]);
    http.interceptors.response.use({
        "createApiClient.use": (r)=>r
    }["createApiClient.use"], {
        "createApiClient.use": async (err)=>{
            const cfg = err.config;
            if (err.response?.status !== 401 || !cfg || cfg._retried) throw err;
            cfg._retried = true;
            // If another request already refreshed after this one was sent, just retry with the new token.
            const sent = String(cfg.headers.Authorization ?? "").replace(/^Bearer /, "");
            const current = auth.getAccessToken();
            const token = current && current !== sent ? current : await refresh();
            cfg.headers.Authorization = `Bearer ${token}`;
            return http(cfg);
        }
    }["createApiClient.use"]);
    return {
        http,
        refresh
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/auth.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createAuthApi",
    ()=>createAuthApi
]);
function createAuthApi({ http }) {
    return {
        /** `next` is an /invite/... path; the backend echoes it back as `redirect` instead of the dashboard. */ onboarding: (workspaceName, next)=>http.post("/auth/onboarding", {
                workspace_name: workspaceName,
                next
            }).then((r)=>r.data),
        logout: ()=>http.post("/auth/logout").then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/chats.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createChatsApi",
    ()=>createChatsApi
]);
function createChatsApi({ http }) {
    return {
        models: ()=>http.get("/models").then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/nodes.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createNodesApi",
    ()=>createNodesApi
]);
function createNodesApi({ http }) {
    return {
        get: (nodeId)=>http.get(`/nodes/${nodeId}`).then((r)=>r.data),
        /** fork_index is assigned server-side (max sibling + 1, retry on unique violation). */ fork: (nodeId)=>http.post(`/nodes/${nodeId}/fork`).then((r)=>r.data),
        /** Server derives the LCA (the merge node's parent) and copies both branches' content. */ merge: (sourceLeafIds)=>http.post("/nodes/merge", {
                source_leaf_ids: sourceLeafIds
            }).then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/projects.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createProjectsApi",
    ()=>createProjectsApi
]);
function createProjectsApi({ http }) {
    return {
        list: ()=>http.get("/projects/").then((r)=>r.data),
        create: (workspaceId, projectName)=>http.post("/projects/", {
                workspace_id: workspaceId,
                project_name: projectName
            }).then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/shares.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createSharesApi",
    ()=>createSharesApi
]);
function createSharesApi({ http }) {
    const project = (slug, projectId)=>`/shares/${slug}/${projectId}`;
    const token = (t)=>`/shares/${encodeURIComponent(t)}`;
    return {
        invite: (slug, projectId, email)=>http.post(`${project(slug, projectId)}/share`, {
                email
            }).then((r)=>r.data),
        list: (slug, projectId)=>http.get(`${project(slug, projectId)}/shares`).then((r)=>r.data.shares),
        revokeShare: (slug, projectId, shareId)=>http.delete(`${project(slug, projectId)}/shares/${shareId}`).then((r)=>r.data),
        revokeInvitation: (slug, projectId, invitationId)=>http.delete(`${project(slug, projectId)}/invitations/${invitationId}`).then((r)=>r.data),
        resend: (slug, projectId, invitationId)=>http.post(`${project(slug, projectId)}/invitations/${invitationId}/resend`).then((r)=>r.data),
        getInvite: (t)=>http.get(token(t)).then((r)=>r.data),
        acceptInvite: (t)=>http.post(`${token(t)}/accept`).then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/trees.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createTreesApi",
    ()=>createTreesApi
]);
function createTreesApi({ http }) {
    return {
        get: (treeId)=>http.get(`/trees/${treeId}`).then((r)=>r.data),
        /** The owner's first visit creates the tree (one empty root node); a sharee gets 404 until then. */ forProject: (projectId)=>http.get(`/projects/${projectId}/tree`).then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/endpoints/workspaces.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "createWorkspacesApi",
    ()=>createWorkspacesApi
]);
function createWorkspacesApi({ http }) {
    return {
        list: ()=>http.get("/workspaces/").then((r)=>r.data)
    };
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/errors.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "apiErrorMessage",
    ()=>apiErrorMessage,
    "apiErrorStatus",
    ()=>apiErrorStatus
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/axios/lib/axios.js [app-client] (ecmascript)");
;
function apiErrorMessage(e, fallback) {
    if (!__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].isAxiosError(e)) return fallback;
    const detail = e.response?.data?.detail;
    return typeof detail === "string" ? detail : fallback;
}
function apiErrorStatus(e) {
    return __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$axios$2f$lib$2f$axios$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["default"].isAxiosError(e) ? e.response?.status : undefined;
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/index.ts [app-client] (ecmascript) <locals>", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "api",
    ()=>api
]);
/**
 * The one entry point features import from: `import { api } from "@/api"`.
 *
 * Each endpoint group is a factory taking an ApiClient, so tests can build one
 * against a fake adapter instead of mocking modules. This file wires the
 * factories to the app's shared client exactly once.
 *
 * Files INSIDE api/ import each other by relative path, never through this
 * barrel -- that would be a cycle.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$auth$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/auth.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$chats$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/chats.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$nodes$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/nodes.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$projects$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/projects.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$shares$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/shares.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$trees$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/trees.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$workspaces$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/endpoints/workspaces.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/session.ts [app-client] (ecmascript)");
// Streaming is not request/response, so it is not part of `api`.
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$stream$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/stream.ts [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$errors$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/errors.ts [app-client] (ecmascript)");
;
;
;
;
;
;
;
;
const api = {
    auth: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$auth$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createAuthApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    chats: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$chats$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createChatsApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    nodes: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$nodes$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createNodesApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    projects: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$projects$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createProjectsApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    shares: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$shares$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createSharesApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    trees: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$trees$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createTreesApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"]),
    workspaces: (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$endpoints$2f$workspaces$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createWorkspacesApi"])(__TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"])
};
;
;
;
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/session.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "apiClient",
    ()=>apiClient,
    "getAccessToken",
    ()=>getAccessToken,
    "isPublicPath",
    ()=>isPublicPath,
    "setAccessToken",
    ()=>setAccessToken,
    "takeTokenFromUrl",
    ()=>takeTokenFromUrl
]);
/**
 * The app's single ApiClient instance, plus where the access token is kept.
 *
 * Split from `client.ts` on purpose: `client.ts` is a pure factory that tests
 * instantiate with a fake adapter, and this file is the one impure singleton
 * the real app uses. Nothing else may call `createApiClient`.
 *
 * The token is held in memory only -- never localStorage, which is readable by
 * any injected script. A reload loses it and falls back to the refresh cookie.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$client$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/client.ts [app-client] (ecmascript)");
;
let accessToken = null;
const getAccessToken = ()=>accessToken;
const setAccessToken = (t)=>{
    accessToken = t;
};
function takeTokenFromUrl() {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("access_token");
    if (!token) return false;
    setAccessToken(token);
    url.searchParams.delete("access_token");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    return true;
}
const isPublicPath = (pathname)=>pathname === "/login" || pathname === "/signup" || pathname.startsWith("/invite/");
const apiClient = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$client$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createApiClient"])({
    baseURL: "/api",
    auth: {
        getAccessToken,
        setAccessToken,
        onAuthFailure: ()=>{
            // To the login screen. Not "/": that redirects to a dashboard, whose
            // first request would 401 again and bounce straight back here.
            //
            // A hard navigation on purpose, not router.push(): this fires from an
            // axios interceptor, where there is no router, and a full reload is what
            // we want anyway -- it drops every store holding data for a session that
            // no longer exists.
            //
            // Skipped on public pages: the invite page must survive a failed refresh
            // and show the invite, and /login must not reload itself.
            // eslint-disable-next-line @next/next/no-location-assign-relative-destination
            if (("TURBOPACK compile-time value", "object") !== "undefined" && !isPublicPath(window.location.pathname)) window.location.assign("/login");
        }
    }
});
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/api/stream.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "sseFrames",
    ()=>sseFrames,
    "streamMessage",
    ()=>streamMessage
]);
async function* sseFrames(body) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    try {
        for(;;){
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, {
                stream: true
            }).replace(/\r\n/g, "\n");
            let idx;
            while((idx = buf.indexOf("\n\n")) !== -1){
                const frame = buf.slice(0, idx);
                buf = buf.slice(idx + 2);
                let event = "message";
                const data = [];
                for (const line of frame.split("\n")){
                    if (line.startsWith("event:")) event = line.slice(6).trim();
                    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
                }
                if (data.length) yield {
                    event,
                    data: data.join("\n")
                };
            }
        }
    } finally{
        reader.releaseLock();
    }
}
async function streamMessage(opts) {
    const send = (token)=>fetch(`${opts.baseURL}/nodes/${opts.nodeId}/messages`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Accept: "text/event-stream",
                ...token ? {
                    Authorization: `Bearer ${token}`
                } : {}
            },
            body: JSON.stringify({
                content: opts.content,
                model: opts.model
            }),
            signal: opts.signal
        });
    let res = await send(opts.getAccessToken());
    if (res.status === 401) res = await send(await opts.refresh());
    if (!res.ok || !res.body) {
        // FastAPI errors are { detail: "..." }; show that instead of a bare status code.
        const detail = await res.json().then((b)=>b.detail, ()=>undefined);
        throw new Error(typeof detail === "string" ? detail : `stream failed: ${res.status}`);
    }
    for await (const { event, data } of sseFrames(res.body)){
        if (event === "token") opts.onEvent({
            type: "token",
            text: JSON.parse(data).text
        });
        else if (event === "done") return void opts.onEvent({
            type: "done",
            ...JSON.parse(data)
        });
        else if (event === "error") return void opts.onEvent({
            type: "error",
            message: JSON.parse(data).message
        });
    }
    // Stream closed with no terminal event: surface it instead of hanging the UI in "streaming".
    opts.onEvent({
        type: "error",
        message: "stream ended unexpectedly"
    });
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/ui/features/auth/RootRedirect.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "RootRedirect",
    ()=>RootRedirect
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$compiler$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/next/dist/compiled/react/compiler-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/next/navigation.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$index$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/frontend/src/api/index.ts [app-client] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$ui$2f$features$2f$auth$2f$useSessionBoot$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/ui/features/auth/useSessionBoot.ts [app-client] (ecmascript)");
var _s = __turbopack_context__.k.signature();
"use client";
;
;
;
;
;
function RootRedirect() {
    _s();
    const $ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$compiler$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["c"])(5);
    if ($[0] !== "58f8cb33c38f07ffbe1754ecedcbf38785bf5ed826b670e3106055354a461b58") {
        for(let $i = 0; $i < 5; $i += 1){
            $[$i] = Symbol.for("react.memo_cache_sentinel");
        }
        $[0] = "58f8cb33c38f07ffbe1754ecedcbf38785bf5ed826b670e3106055354a461b58";
    }
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRouter"])();
    const session = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$ui$2f$features$2f$auth$2f$useSessionBoot$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useSessionBoot"])();
    let t0;
    let t1;
    if ($[1] !== router || $[2] !== session) {
        t0 = ({
            "RootRedirect[useEffect()]": ()=>{
                if (session !== "ready") {
                    return;
                }
                __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$index$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$locals$3e$__["api"].workspaces.list().then({
                    "RootRedirect[useEffect() > (anonymous)()]": (list)=>{
                        router.replace(list.length ? `/${list[0].workspace_slug}/dashboard` : "/onboarding");
                    }
                }["RootRedirect[useEffect() > (anonymous)()]"]);
            }
        })["RootRedirect[useEffect()]"];
        t1 = [
            session,
            router
        ];
        $[1] = router;
        $[2] = session;
        $[3] = t0;
        $[4] = t1;
    } else {
        t0 = $[3];
        t1 = $[4];
    }
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])(t0, t1);
    return null;
}
_s(RootRedirect, "gRfaAe+EO8KLiH/8+BXqez+92wU=", false, function() {
    return [
        __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRouter"],
        __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$ui$2f$features$2f$auth$2f$useSessionBoot$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useSessionBoot"]
    ];
});
_c = RootRedirect;
var _c;
__turbopack_context__.k.register(_c, "RootRedirect");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/frontend/src/ui/features/auth/useSessionBoot.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "useSessionBoot",
    ()=>useSessionBoot
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$compiler$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/next/dist/compiled/react/compiler-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$index$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/frontend/src/api/index.ts [app-client] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/frontend/src/api/session.ts [app-client] (ecmascript)");
var _s = __turbopack_context__.k.signature();
"use client";
;
;
;
function useSessionBoot() {
    _s();
    const $ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$compiler$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["c"])(3);
    if ($[0] !== "25ea84574330d5dc363702b27886f430935d774833880e9410e2f39776f4dce9") {
        for(let $i = 0; $i < 3; $i += 1){
            $[$i] = Symbol.for("react.memo_cache_sentinel");
        }
        $[0] = "25ea84574330d5dc363702b27886f430935d774833880e9410e2f39776f4dce9";
    }
    const [state, setState] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("loading");
    let t0;
    let t1;
    if ($[1] === Symbol.for("react.memo_cache_sentinel")) {
        t0 = ({
            "useSessionBoot[useEffect()]": ()=>{
                (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["takeTokenFromUrl"])();
                const ready = (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["getAccessToken"])() ? Promise.resolve() : __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$src$2f$api$2f$session$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["apiClient"].refresh();
                ready.then({
                    "useSessionBoot[useEffect() > ready.then(arg0)]": ()=>setState("ready")
                }["useSessionBoot[useEffect() > ready.then(arg0)]"], {
                    "useSessionBoot[useEffect() > ready.then(arg1)]": ()=>setState("anonymous")
                }["useSessionBoot[useEffect() > ready.then(arg1)]"]);
            }
        })["useSessionBoot[useEffect()]"];
        t1 = [];
        $[1] = t0;
        $[2] = t1;
    } else {
        t0 = $[1];
        t1 = $[2];
    }
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$frontend$2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])(t0, t1);
    return state;
}
_s(useSessionBoot, "wM9t3JDpDZMRIYCr4B3khtHRzgk=");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
]);

//# sourceMappingURL=frontend_src_0m6oe7j._.js.map