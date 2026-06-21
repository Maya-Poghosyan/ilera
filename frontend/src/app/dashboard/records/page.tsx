"use client";

import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  createJournal,
  createTimekeeping,
  deleteJournalEntry,
  deleteTimekeepingEntry,
  getRenewal,
  listJournal,
  listTimekeeping,
  updateRenewal,
} from "@/lib/api";
import type { JournalEntry, RenewalInfo, TimekeepingEntry } from "@/lib/types";

export default function RecordsPage() {
  const [caseId, setCaseId] = useState<string | null>(null);
  const [timekeeping, setTimekeeping] = useState<TimekeepingEntry[]>([]);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [renewal, setRenewal] = useState<RenewalInfo | null>(null);
  const [loading, setLoading] = useState(true);

  // Timekeeping form
  const [showTkForm, setShowTkForm] = useState(false);
  const [tkDate, setTkDate] = useState("");
  const [tkHours, setTkHours] = useState("");
  const [tkTasks, setTkTasks] = useState("");

  // Journal form
  const [showJnForm, setShowJnForm] = useState(false);
  const [jnDate, setJnDate] = useState("");
  const [jnText, setJnText] = useState("");

  // Renewal editing
  const [editingRenewal, setEditingRenewal] = useState(false);
  const [renewalDate, setRenewalDate] = useState("");

  const loadData = useCallback(async (id: string) => {
    try {
      const [tk, jn, rn] = await Promise.all([
        listTimekeeping(id),
        listJournal(id),
        getRenewal(id),
      ]);
      setTimekeeping(tk);
      setJournal(jn);
      setRenewal(rn);
    } catch {
      // API may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("ilera_case_id") : null;
    if (stored) {
      setCaseId(stored);
      loadData(stored);
    } else {
      setLoading(false);
    }
  }, [loadData]);

  const fallEntries = journal.filter((j) => j.fall_flagged);

  const handleAddTimekeeping = async () => {
    if (!caseId || !tkDate || !tkHours) return;
    await createTimekeeping({
      case_id: caseId,
      date: tkDate,
      hours: parseFloat(tkHours),
      tasks: tkTasks
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    });
    setShowTkForm(false);
    setTkDate("");
    setTkHours("");
    setTkTasks("");
    await loadData(caseId);
  };

  const handleDeleteTimekeeping = async (id: string) => {
    if (!caseId) return;
    await deleteTimekeepingEntry(id, caseId);
    await loadData(caseId);
  };

  const handleAddJournal = async () => {
    if (!caseId || !jnDate || !jnText) return;
    await createJournal({
      case_id: caseId,
      date: jnDate,
      text: jnText,
    });
    setShowJnForm(false);
    setJnDate("");
    setJnText("");
    await loadData(caseId);
  };

  const handleDeleteJournal = async (id: string) => {
    if (!caseId) return;
    await deleteJournalEntry(id, caseId);
    await loadData(caseId);
  };

  const handleSaveRenewal = async () => {
    if (!caseId) return;
    await updateRenewal(caseId, { due_date: renewalDate });
    setEditingRenewal(false);
    await loadData(caseId);
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  if (!caseId && !loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl font-bold">Records &amp; Renewal</h1>
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              Complete the intake wizard first to create a case profile, then return here to track
              timekeeping, journal entries, and renewals.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-4xl font-bold">Records &amp; Renewal</h1>
        <div className="flex items-center gap-2">
          {editingRenewal ? (
            <>
              <Input
                type="date"
                value={renewalDate}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setRenewalDate(e.target.value)}
                className="w-40"
              />
              <Button size="sm" onClick={handleSaveRenewal}>Save</Button>
              <Button size="sm" variant="outline" onClick={() => setEditingRenewal(false)}>Cancel</Button>
            </>
          ) : (
            <button
              className="text-sm font-medium text-muted-foreground hover:text-foreground"
              onClick={() => {
                setRenewalDate(renewal?.due_date ?? "");
                setEditingRenewal(true);
              }}
            >
              Renewal due: {renewal?.due_date ? formatDate(renewal.due_date) : "Not set (click to edit)"}
            </button>
          )}
        </div>
      </div>

      <p className="text-2xl font-semibold">
        Renewal for {renewal?.due_date
          ? `${new Date(renewal.due_date + "T00:00:00").getFullYear() - 1}–${new Date(renewal.due_date + "T00:00:00").getFullYear()}`
          : `${new Date().getFullYear()}–${new Date().getFullYear() + 1}`
        } due {renewal?.due_date ? formatDate(renewal.due_date) + ", " + new Date(renewal.due_date + "T00:00:00").getFullYear() : "1 year from submission"}
      </p>

      {fallEntries.length > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <CardContent className="flex items-start gap-3 py-4 text-sm">
            <span aria-hidden>🚩</span>
            <p>
              You logged <strong>a fall</strong> on{" "}
              <strong>{formatDate(fallEntries[0].date)}</strong>. Create a state incident report?{" "}
              <a className="font-medium underline" href="/dashboard/documents">
                Go to Documents
              </a>
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Timekeeping */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Timekeeping</h2>
            <Button size="sm" variant="outline" onClick={() => setShowTkForm(true)}>
              + Entry
            </Button>
          </div>

          {showTkForm && (
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="space-y-1">
                  <Label htmlFor="tk-date">Date</Label>
                  <Input
                    id="tk-date"
                    type="date"
                    value={tkDate}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkDate(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-hours">Hours</Label>
                  <Input
                    id="tk-hours"
                    type="number"
                    step="0.5"
                    min="0"
                    value={tkHours}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkHours(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-tasks">Tasks (comma-separated)</Label>
                  <Input
                    id="tk-tasks"
                    value={tkTasks}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkTasks(e.target.value)}
                    placeholder="Bathing, meals, medication"
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleAddTimekeeping}>Add</Button>
                  <Button size="sm" variant="outline" onClick={() => setShowTkForm(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {timekeeping.map((t) => (
            <Card key={t.id}>
              <CardHeader className="flex flex-row items-center justify-between py-3">
                <CardTitle className="text-sm">{formatDate(t.date)}</CardTitle>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t.hours} hrs</span>
                  <button
                    onClick={() => handleDeleteTimekeeping(t.id)}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete entry"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </CardHeader>
              <CardContent className="py-0 pb-3 text-sm text-muted-foreground">
                {t.tasks.join(", ") || "No tasks recorded"}
              </CardContent>
            </Card>
          ))}

          {!loading && timekeeping.length === 0 && (
            <p className="text-sm text-muted-foreground">No timekeeping entries yet.</p>
          )}

          <Button size="sm" disabled title="Coming soon — Browserbase automation">
            Submit timesheet to IHSS portal (coming soon)
          </Button>
        </section>

        {/* Care journal */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Care journal</h2>
            <Button size="sm" variant="outline" onClick={() => setShowJnForm(true)}>
              + Entry
            </Button>
          </div>

          {showJnForm && (
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="space-y-1">
                  <Label htmlFor="jn-date">Date</Label>
                  <Input
                    id="jn-date"
                    type="date"
                    value={jnDate}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setJnDate(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="jn-text">Entry</Label>
                  <Textarea
                    id="jn-text"
                    value={jnText}
                    onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setJnText(e.target.value)}
                    placeholder="How was today's care?"
                    rows={3}
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleAddJournal}>Add</Button>
                  <Button size="sm" variant="outline" onClick={() => setShowJnForm(false)}>Cancel</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {journal.map((j) => (
            <Card key={j.id} className={j.fall_flagged ? "border-amber-300" : ""}>
              <CardHeader className="flex flex-row items-center justify-between py-3">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm">{formatDate(j.date)}</CardTitle>
                  {j.fall_flagged && (
                    <span className="text-xs font-medium text-amber-600">Fall flagged</span>
                  )}
                </div>
                <button
                  onClick={() => handleDeleteJournal(j.id)}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Delete entry"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </CardHeader>
              <CardContent className="py-0 pb-3 text-sm text-muted-foreground">{j.text}</CardContent>
            </Card>
          ))}

          {!loading && journal.length === 0 && (
            <p className="text-sm text-muted-foreground">No journal entries yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}
