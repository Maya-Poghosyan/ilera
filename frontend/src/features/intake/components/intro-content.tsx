import type { IntakePage } from "@/features/intake/flow";

/** A section's introduction: its text (with one emphasized phrase) and where to find documents. */
export function IntroContent({ page }: { page: IntakePage }) {
  const text = page.introText ?? "";
  const emphasis = page.introEmphasis;
  const at = emphasis ? text.indexOf(emphasis) : -1;
  return (
    <div className="space-y-4 text-base text-muted-foreground">
      <p>{emphasis && at >= 0 ? <>{text.slice(0, at)}<strong className="font-semibold">{emphasis}</strong>{text.slice(at + emphasis.length)}</> : page.introText}</p>
      {page.introDocuments && (
        <table className="w-full table-fixed text-left text-sm sm:text-base">
          <thead className="text-foreground">
            <tr>
              <th scope="col" className="w-[45%] pb-3 pr-6 font-medium">Document</th>
              <th scope="col" className="pb-3 font-medium">Where to find it</th>
            </tr>
          </thead>
          <tbody>
            {page.introDocuments.map((item) => (
              <tr key={item.document} className="align-top">
                <td className="py-2 pr-6">{item.document}</td>
                <td className="py-2">{item.location}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {emphasis && at < 0 && <p><strong className="font-semibold">{emphasis}</strong></p>}
    </div>
  );
}
