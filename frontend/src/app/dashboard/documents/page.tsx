import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const docs = [
  { name: "IHSS Application (SOC 295)", status: "Auto-filled · ready to review" },
  { name: "Medi-Cal Application", status: "Auto-filled · needs income proof" },
  { name: "Combined application packet.pdf", status: "Generated" },
];

export default function DocumentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Documents</h1>
          <p className="text-sm text-muted-foreground">
            Auto-populated with completed forms. Create new documents as needed.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">+ Document</Button>
          <Button size="sm">+ Incident Report</Button>
        </div>
      </div>

      <div className="space-y-3">
        {docs.map((d) => (
          <Card key={d.name}>
            <CardHeader className="flex flex-row items-center justify-between py-4">
              <CardTitle className="text-base">{d.name}</CardTitle>
              <span className="text-xs text-muted-foreground">{d.status}</span>
            </CardHeader>
            <CardContent className="py-0 pb-4">
              <Button variant="ghost" size="sm">
                View
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
