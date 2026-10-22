"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Button, Frame, Input, Link, Loading, Panel, Text } from "@/ui/library";
import { FieldGuide } from "@/ui/features/settings/FieldGuide";
import { LightingPicker } from "@/ui/features/settings/LightingPicker";
import { useSignOut } from "@/ui/features/settings/useSignOut";
import { Contents } from "./components/Contents";
import { IdBadge } from "./components/IdBadge";
import { WorkspaceRow } from "./components/WorkspaceRow";
import { useAccount } from "./useAccount";
import "./Account.css";

/* The settings page's content: the reader's ID badge and an index on the
 * left, and the file's sections on the right -- profile, workspaces,
 * appearance, field guide, account. Data and actions: useAccount.ts. */

const SECTIONS = [
  { id: "profile", label: "Profile" },
  { id: "workspaces", label: "Workspaces" },
  { id: "appearance", label: "Appearance" },
  { id: "guide", label: "Field guide" },
  { id: "account", label: "Account" },
] as const;

export function Account() {
  const { state, actionError, renameSelf, renameWorkspace, deleteWorkspace } = useAccount();
  const signOut = useSignOut();
  // the slug this page sits under, kept current by renames (history.replaceState): the way back to the board
  const slug = usePathname().split("/")[1] ?? "";
  // Back returns where settings was opened from (?from=, set by the workspace's Settings panel), else to the board.
  // Only a path on this site: it comes from the URL, so a full or protocol-relative URL ("//", "/\") could send the reader off-site.
  const from = useSearchParams().get("from");
  const back = from && /^\/(?![/\\])/.test(from) ? from : null;
  const active = useReading(state.status === "ready");

  return (
    <Frame gap="6" className="account">
      <Frame as="header" gap="1" className="account-head">
        <Link href={back ?? `/${slug}/dashboard`} className="account-back">
          <Text as="span" size="s" content={back ? "← Back" : "← Back to the board"} />
        </Link>
        <Text as="span" size="xs" className="account-kicker" content="Personnel file" />
        <Text as="h1" size="display" hierarchy="primary" className="account-title" content="Settings" />
      </Frame>

      {state.status === "loading" && <Loading label="Pulling your file…" />}
      {state.status === "error" && <Text role="alert" content={state.message} />}

      {state.status === "ready" && (
        <Frame direction="row" gap="8" align="start" className="account-body">
          <Frame gap="8" align="center" className="account-aside">
            <IdBadge account={state.account} />
            <Contents sections={SECTIONS} active={active.id} onPick={active.pick} />
          </Frame>

          <Frame gap="6" className="account-sections">
            {actionError && <Text role="alert" size="s" className="account-error" content={actionError} />}

            <Section id="profile" number={1} title="Profile" note="How you appear to people you share a case with.">
              <NameForm name={state.account.name} onSave={renameSelf} />
              <Frame gap="1">
                <Text as="span" size="xs" hierarchy="tertiary" content="Email" />
                <Text size="s" hierarchy="secondary" content={state.account.email} />
              </Frame>
              <Text size="xs" hierarchy="tertiary" content="Your photo and email come from your Google account." />
            </Section>

            <Section id="workspaces" number={2} title="Workspaces" note="Each workspace is a folder of cases on your dashboard.">
              <Frame as="ol" gap="2" className="workspace-list">
                {state.workspaces.map((w) => (
                  <WorkspaceRow
                    key={w.workspace_id}
                    workspace={w}
                    projects={state.projectCounts[w.workspace_id] ?? 0}
                    current={w.workspace_slug === slug}
                    canDelete={state.workspaces.length > 1}
                    onRename={(name) => renameWorkspace(w.workspace_id, name)}
                    onDelete={() => deleteWorkspace(w.workspace_id)}
                  />
                ))}
              </Frame>
            </Section>

            <Section id="appearance" number={3} title="Appearance" note="Light the board your way. Kept in this browser.">
              <Frame gap="2" className="account-lighting">
                <Text as="h3" id="account-lighting" size="xs" className="settings-heading" content="Lighting" />
                <LightingPicker labelledBy="account-lighting" />
              </Frame>
            </Section>

            <Section id="guide" number={4} title="Field guide" note="The moves the board doesn't spell out.">
              <FieldGuide />
            </Section>

            <Section id="account" number={5} title="Account">
              <Frame direction="row" justify="between" align="center" gap="4" className="account-row">
                <Frame gap="0">
                  <Text size="s" hierarchy="primary" content="Sign out" />
                  <Text size="xs" hierarchy="tertiary" content="Ends your session in this browser." />
                </Frame>
                <Button size="s" icon="logout" label="Sign out" showIcon onClick={signOut} />
              </Frame>
              <Frame direction="row" justify="between" align="center" gap="4" className="account-row">
                <Frame gap="0">
                  <Text size="s" hierarchy="primary" content="Delete account" />
                  <Text size="xs" hierarchy="tertiary" content="Closes your file for good: every workspace and case goes with it." />
                </Frame>
                {/* TODO(backend): GET /auth/reauth/google needs a Bearer token, which a browser redirect can't carry, so this can't be reached yet. */}
                <Button size="s" icon="person_remove" label="Not available yet" showIcon disabled />
              </Frame>
            </Section>
          </Frame>
        </Frame>
      )}
    </Frame>
  );
}

/** Which section is being read: the one crossing a line near the top of the
 * window, or the last once the page is scrolled to the bottom (it may never
 * reach that line). A pick from Contents counts at once and holds while the
 * page scrolls to it, or a short last section would lose to the bottom rule. */
function useReading(ready: boolean) {
  const [id, setId] = useState<string>(SECTIONS[0].id);
  const pickedAt = useRef(0);
  useEffect(() => {
    if (!ready) return;
    const set = (next: string) => Date.now() - pickedAt.current > 1000 && setId(next);
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && set(e.target.id)),
      { rootMargin: "-20% 0px -70% 0px" },
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    });
    const onScroll = () => {
      if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) set(SECTIONS[SECTIONS.length - 1].id);
    };
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      removeEventListener("scroll", onScroll);
    };
  }, [ready]);
  const pick = (next: string) => {
    pickedAt.current = Date.now();
    setId(next);
  };
  return { id, pick };
}

/* One section of the file: a sheet with a manila band across its head. */
function Section({ id, number, title, note, children }: { id: string; number: number; title: string; note?: string; children: ReactNode }) {
  return (
    <Panel as="section" id={id} elevation="floating" className="account-section" aria-labelledby={`${id}-heading`}>
      <Frame gap="4">
        <Frame as="header" gap="1" className="account-section-head">
          {/* the folder's tab, standing up off the sheet */}
          <Text as="span" size="xxs" className="account-section-tab" content={`Section ${number}`} />
          <Text as="h2" id={`${id}-heading`} size="xl" hierarchy="primary" className="account-section-title" content={title} />
          {note && <Text size="xs" hierarchy="secondary" content={note} />}
        </Frame>
        {children}
      </Frame>
    </Panel>
  );
}

/* The name, editable in place; Save lights up once it has changed. */
function NameForm({ name, onSave }: { name: string; onSave(name: string): void }) {
  const [draft, setDraft] = useState(name);
  const trimmed = draft.trim();
  function submit(e: FormEvent) {
    e.preventDefault();
    if (trimmed && trimmed !== name) onSave(trimmed);
  }
  return (
    <Frame as="form" gap="1" onSubmit={submit}>
      <Text as="label" htmlFor="account-name" size="xs" hierarchy="tertiary" content="Name" />
      <Frame direction="row" gap="2" align="center">
        <Panel className="settings-field account-name-field">
          <Input id="account-name" value={draft} maxLength={100} autoComplete="name" onChange={(e) => setDraft(e.target.value)} />
        </Panel>
        <Button type="submit" hierarchy="primary" size="s" label="Save" disabled={!trimmed || trimmed === name} />
      </Frame>
    </Frame>
  );
}
