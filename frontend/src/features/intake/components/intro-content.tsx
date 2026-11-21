import type { IntakePage } from "@/features/intake/flow";

/** A section's introduction: its text, with one emphasized phrase. */
export function IntroContent({ page }: { page: IntakePage }) {
  const text = page.introText ?? "";
  const emphasis = page.introEmphasis;
  const at = emphasis ? text.indexOf(emphasis) : -1;
  return (
    <div className="space-y-4 text-base text-muted-foreground">
      <p>{emphasis && at >= 0 ? <>{text.slice(0, at)}<strong className="font-semibold">{emphasis}</strong>{text.slice(at + emphasis.length)}</> : page.introText}</p>
      {emphasis && at < 0 && <p><strong className="font-semibold">{emphasis}</strong></p>}
    </div>
  );
}
