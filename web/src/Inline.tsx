// Renders text where `backticked` parts are shown as code. The summaries use that for names.
export function Inline({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : <span key={i}>{part}</span>))}
    </>
  );
}
