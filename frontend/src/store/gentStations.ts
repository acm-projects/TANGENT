import { useCallback } from "react";

/* Stations: the places on screen Gent can go. Any component becomes one by putting `useGentStation(key)` on an
 * element as its ref; Gent then travels there, inks its outline and perches on top (GentPresence). Keys:
 *   home           his socket in the dock
 *   node:<id>      a card on the map (travel between cards follows the strings)
 *   notes          the Field Notes, open or folded into their tile
 *   tool:<name>    a toolbar tile, e.g. tool:search while he searches
 * A station that unmounts and mounts again (a card re-rendered, the notes folded) keeps its key, so Gent stays. */

export const HOME = "home";
export const NOTES = "notes";
export const SEARCH = "tool:search";
export const nodeStation = (id: string) => `node:${id}`;
export const nodeOf = (key: string) => (key.startsWith("node:") ? key.slice(5) : null);

const stations = new Map<string, HTMLElement>();
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((fn) => fn());

export const stationEl = (key: string) => {
  const el = stations.get(key);
  return el?.isConnected ? el : undefined;
};

export function subscribeStations(fn: () => void) {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}

/** A ref that makes its element the station `key`. */
export function useGentStation<T extends HTMLElement>(key: string) {
  return useCallback(
    (el: T | null) => {
      if (!el) return;
      stations.set(key, el);
      notify();
      return () => {
        if (stations.get(key) !== el) return;
        stations.delete(key);
        notify();
      };
    },
    [key],
  );
}
