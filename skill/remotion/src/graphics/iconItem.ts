import type { IconItem } from "../types";

/** An enumeration / compare point may be a plain string or {text, icon}. */
export const itemText = (it: IconItem): string => (typeof it === "string" ? it : it.text);
export const itemIcon = (it: IconItem): string | undefined =>
  typeof it === "string" ? undefined : it.icon;
