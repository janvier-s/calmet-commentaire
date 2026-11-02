// The text a proposal leaves, around its change, as runs to typeset: no DOM, so node tests it.

/** [{t, italic, mark}] for the new text of `change` ({old, new}, italics as _underscores_): the words around
 * the change (`around` letters either side, cut at a space), `mark` on what changed. `cut`: ["…", "…"] where
 * the text goes on. */
export function previewRuns(change, around = 70) {
  const o = change.old, n = change.new;
  let i = 0;
  while (i < o.length && i < n.length && o[i] === n[i]) i++;
  let j = 0;
  while (j < o.length - i && j < n.length - i && o[o.length - 1 - j] === n[n.length - 1 - j]) j++;
  let end = Math.max(n.length - j, i);
  while (end > i && n[end - 1] === "_") end--;  // a mark the change ends on is no changed word
  let a = Math.max(0, i - around), b = Math.min(n.length, end + around);
  if (a > 0) { const s = n.indexOf(" ", a); if (s >= 0 && s < i) a = s + 1; }
  if (b < n.length) { const s = n.lastIndexOf(" ", b); if (s > end) b = s; }
  // the mark takes in the whole words the change touches (an underscore put before a word marks the word)
  let ma = i, mb = end;
  while (ma > a && /[\p{L}\p{N}'’-]/u.test(n[ma - 1])) ma--;
  while (mb < b && /[\p{L}\p{N}'’-]/u.test(n[mb])) mb++;
  let italic = (n.slice(0, a).split("_").length - 1) % 2 === 1;
  const runs = [];
  for (let k = a; k < b; k++) {
    if (n[k] === "_") { italic = !italic; continue; }
    if ((n[k] === "^" && n[k + 1] === "{") || (n[k] === "{" && n[k - 1] === "^") || (n[k] === "}" && n.lastIndexOf("^{", k) > n.lastIndexOf("}", k - 1))) continue;  // ^{(e)}: (e)
    const mark = k >= ma && k < mb, last = runs[runs.length - 1];
    if (last && last.italic === italic && last.mark === mark) last.t += n[k];
    else runs.push({ t: n[k], italic, mark });
  }
  return { runs, cut: [a > 0, b < n.length] };
}
