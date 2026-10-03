function unescape(text) {
  return String(text).replace(/\\r\\n/g, "\n").replace(/\\n/g, "\n").replace(/\\t/g, "\t");
}

function inline(text, key = "t") {
  const pattern = /(`[^`]+`)|(\*\*(.+?)\*\*)|(\*(.+?)\*)/gs;
  const nodes = [];
  let last = 0;
  let index = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const id = `${key}-${index}`;
    if (match[1]) nodes.push(<code key={id}>{match[1].slice(1, -1)}</code>);
    else if (match[2]) nodes.push(<strong key={id}>{inline(match[3], id)}</strong>);
    else nodes.push(<em key={id}>{inline(match[5], id)}</em>);
    last = match.index + match[0].length;
    index += 1;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function RichText({ text, className }) {
  if (!text) return null;
  return <div className={`rich ${className || ""}`.trim()}>{inline(unescape(text))}</div>;
}
