/** Parse a string with {curly} emphasis markers into segments.
 * "kannst du deine {Steuerlast} senken" → [{t:"kannst du deine ",bold:false},
 * {t:"Steuerlast",bold:true},{t:" senken",bold:false}] */
export type Seg = { t: string; bold: boolean };

export function parseBold(s: string): Seg[] {
  const out: Seg[] = [];
  const re = /\{([^}]*)\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ t: s.slice(last, m.index), bold: false });
    out.push({ t: m[1], bold: true });
    last = re.lastIndex;
  }
  if (last < s.length) out.push({ t: s.slice(last), bold: false });
  return out;
}

export const plain = (s: string) => s.replace(/[{}]/g, "");
