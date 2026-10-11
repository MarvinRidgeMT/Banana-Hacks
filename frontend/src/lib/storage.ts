/* localStorage can throw (Safari private mode, blocked cookies, sandboxed
 * iframes), so every access is guarded and failures fall back to defaults. */

export function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice lasts for this page view only */
  }
}
