"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getFormDownloadUrl, listForms } from "@/lib/api";
import type { FormSchema } from "@/lib/types";

export default function DocumentsPage() {
  const [forms, setForms] = useState<FormSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("ilera_case_id") : null;
    if (stored) setCaseId(stored);
    listForms()
      .then((data) => setForms(data.forms))
      .catch(() => setForms([]))
      .finally(() => setLoading(false));
  }, []);

  function handleDownload(formId: string) {
    if (!caseId) return;
    setDownloading(formId);
    const url = getFormDownloadUrl(formId, caseId);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${formId}_${caseId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => setDownloading(null), 2000);
  }

  const programGroups = forms.reduce<Record<string, FormSchema[]>>((acc, f) => {
    const key = `${f.agency} / ${f.program}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(f);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Documents</h1>
          <p className="text-sm text-muted-foreground">
            Auto-filled government benefit forms. Select a form and download the
            pre-populated PDF.
          </p>
        </div>
      </div>

      {!caseId && (
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              Complete the intake wizard first to create a case profile, then
              return here to download auto-filled forms.
            </p>
          </CardContent>
        </Card>
      )}

      {loading && (
        <p className="text-sm text-muted-foreground">Loading forms...</p>
      )}

      {Object.entries(programGroups).map(([group, groupForms]) => (
        <div key={group} className="space-y-3">
          <h2 className="text-lg font-semibold">{group}</h2>
          {groupForms.map((f) => {
            const hasMappings = f.mapped_fields > 0;
            return (
              <Card key={f.form_id}>
                <CardHeader className="flex flex-row items-center justify-between py-4">
                  <div className="flex items-center gap-3">
                    <CardTitle className="text-base">{f.title}</CardTitle>
                    <Badge variant={hasMappings ? "default" : "secondary"}>
                      {f.form_id}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {f.mapped_fields}/{f.total_pdf_fields} fields mapped
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="flex items-center gap-2 py-0 pb-4">
                  <Button
                    size="sm"
                    disabled={!caseId || downloading === f.form_id}
                    onClick={() => handleDownload(f.form_id)}
                  >
                    {downloading === f.form_id
                      ? "Downloading..."
                      : "Download Filled PDF"}
                  </Button>
                  {f.source_url && (
                    <a
                      href={f.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                    >
                      Source
                    </a>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      ))}
    </div>
  );
}
