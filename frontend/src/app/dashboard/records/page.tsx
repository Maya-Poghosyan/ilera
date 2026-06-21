"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import type { JournalEntry, RenewalInfo, ServiceType, TimekeepingEntry } from "@/lib/types";

const SERVICE_LABELS: Record<ServiceType, string> = {
  personal_care: "Personal Care",
  domestic: "Domestic",
  paramedical: "Paramedical",
  accompaniment: "Accompaniment",
};

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
  const [tkStartTime, setTkStartTime] = useState("");
  const [tkEndTime, setTkEndTime] = useState("");
  const [tkServiceType, setTkServiceType] = useState<ServiceType>("personal_care");
  const [tkTasks, setTkTasks] = useState("");
  const [tkNotes, setTkNotes] = useState("");

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
      start_time: tkStartTime || undefined,
      end_time: tkEndTime || undefined,
      service_type: tkServiceType,
      tasks: tkTasks
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      notes: tkNotes || undefined,
    });
    setShowTkForm(false);
    setTkDate("");
    setTkHours("");
    setTkStartTime("");
    setTkEndTime("");
    setTkServiceType("personal_care");
    setTkTasks("");
    setTkNotes("");
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
              timesheets, journal entries, and renewals.
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
          ? `${new Date(renewal.due_date + "T00:00:00").getFullYear() - 1}\u2013${new Date(renewal.due_date + "T00:00:00").getFullYear()}`
          : `${new Date().getFullYear()}\u2013${new Date().getFullYear() + 1}`
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
        {/* Timesheets */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold">Timesheets</h2>
              <a
                href="https://www.etimesheets.ihss.ca.gov"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-serif text-sm text-black underline hover:text-black/70"
              >
                Submit timesheet to IHSS portal
                <ExternalLink className="size-3.5" />
              </a>
            </div>
            <Button size="sm" variant="outline" onClick={() => setShowTkForm(true)}>
              + Entry
            </Button>
          </div>

          {showTkForm && (
            <Card>
              <CardContent className="space-y-3 py-4">
                <div className="grid grid-cols-2 gap-3">
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
                    <Label htmlFor="tk-hours">Total Hours</Label>
                    <Input
                      id="tk-hours"
                      type="number"
                      step="0.25"
                      min="0"
                      max="24"
                      value={tkHours}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkHours(e.target.value)}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label htmlFor="tk-start">Start Time</Label>
                    <Input
                      id="tk-start"
                      type="time"
                      value={tkStartTime}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkStartTime(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="tk-end">End Time</Label>
                    <Input
                      id="tk-end"
                      type="time"
                      value={tkEndTime}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkEndTime(e.target.value)}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label>Service Type</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(SERVICE_LABELS) as ServiceType[]).map((st) => (
                      <Button
                        key={st}
                        type="button"
                        variant={tkServiceType === st ? "default" : "outline"}
                        size="sm"
                        onClick={() => setTkServiceType(st)}
                      >
                        {SERVICE_LABELS[st]}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-tasks">Activities (comma-separated)</Label>
                  <Input
                    id="tk-tasks"
                    value={tkTasks}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkTasks(e.target.value)}
                    placeholder="Bathing, dressing, meal prep, medication"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="tk-notes">Notes</Label>
                  <Input
                    id="tk-notes"
                    value={tkNotes}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTkNotes(e.target.value)}
                    placeholder="Any additional details"
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
              <CardContent className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-base font-semibold">{formatDate(t.date)}</span>
                  <button
                    onClick={() => handleDeleteTimekeeping(t.id)}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete entry"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  <span>Hours: <span className="font-medium">{t.hours}</span></span>
                  {t.start_time && t.end_time && <span> ({t.start_time}\u2013{t.end_time})</span>}
                  {" · "}{SERVICE_LABELS[t.service_type] ?? t.service_type}
                  {" · "}{t.tasks.length > 0 ? t.tasks.join(", ") : "No activities"}
                  {t.notes && <span> · {t.notes}</span>}
                </p>
              </CardContent>
            </Card>
          ))}

          {!loading && timekeeping.length === 0 && (
            <p className="text-sm text-muted-foreground">No timesheet entries yet.</p>
          )}
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
              <CardContent className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-base font-semibold">{formatDate(j.date)}</span>
                  <button
                    onClick={() => handleDeleteJournal(j.id)}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Delete entry"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">{j.text}</p>
              </CardContent>
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
