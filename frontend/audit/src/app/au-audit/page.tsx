'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface GroupedFolder {
  name: string;
  path: string;
  job_count: number;
  completed_jobs: number;
  pending_jobs: number;
  created: string;
}

interface JobStatus {
  job_id: string;
  hawb?: string;
  dhl_job_number?: string;
  broker?: string;
  status: 'completed' | 'pending' | 'failed';
  has_pdfs: boolean;
}

interface JobListResponse {
  success: boolean;
  folder_name: string;
  jobs: JobStatus[];
  total: number;
  completed: number;
  pending: number;
}

interface ListGroupedFoldersResponse {
  success: boolean;
  input_folder: string;
  folders: GroupedFolder[];
}

interface AUAuditJobResult {
  job_id: string;
  success: boolean;
  error?: string;
  job_folder?: string;
  csv_path?: string;
  extraction?: {
    audit_month: string;
    entry_number: string;
    waybill_number: string;
  };
  header_validation?: Record<string, string>;
  auditor_comments?: string;
  auditor?: string;
}

interface AUAuditBatchResponse {
  success: boolean;
  message: string;
  run_id?: string;
  run_path?: string;
  total_jobs: number;
  successful_jobs: number;
  failed_jobs: number;
  skipped_jobs: number;
  csv_path?: string;
  xlsx_path?: string;
  results: AUAuditJobResult[];
}

export default function AUAuditPage() {
  const router = useRouter();
  const [folders, setFolders] = useState<GroupedFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<AUAuditBatchResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [jobList, setJobList] = useState<JobListResponse | null>(null);

  useEffect(() => {
    loadGroupedFolders();
  }, []);

  useEffect(() => {
    const fetchJobs = async () => {
      if (!selectedFolder) {
        setJobList(null);
        return;
      }
      try {
        const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${endpoint}/api/au-audit/jobs?folder_name=${encodeURIComponent(selectedFolder)}`);
        if (!response.ok) throw new Error('Failed to load job list');
        const data: JobListResponse = await response.json();
        setJobList(data);
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : 'Failed to load job list');
      }
    };
    fetchJobs();
  }, [selectedFolder]);

  const loadGroupedFolders = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${endpoint}/api/au-audit/grouped-folders`);
      if (!response.ok) throw new Error('Failed to load grouped folders');
      const data: ListGroupedFoldersResponse = await response.json();
      setFolders(data.folders);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load folders');
    } finally {
      setLoading(false);
    }
  };

  const handleRunAudit = async (resumeFailedOnly: boolean = false) => {
    if (!selectedFolder) return;
    setProcessing(true);
    setErrorMsg(null);
    setAuditResult(null);
    try {
      const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const params = new URLSearchParams({
        folder_name: selectedFolder,
        resume_failed_only: resumeFailedOnly.toString()
      });
      const response = await fetch(`${endpoint}/api/au-audit/process?${params}`, { method: 'POST' });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Audit failed');
      }
      const data: AUAuditBatchResponse = await response.json();
      setAuditResult(data);
      await loadGroupedFolders();
      // Trigger job list refresh by resetting selectedFolder
      const folder = selectedFolder;
      setSelectedFolder(null);
      setTimeout(() => setSelectedFolder(folder), 0);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Audit failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleDownloadCSV = () => {
    if (!auditResult?.csv_path) return;
    const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    window.open(`${endpoint}/api/au-audit/download-csv?csv_path=${encodeURIComponent(auditResult.csv_path)}`, '_blank');
  };

  const handleDownloadXLSX = () => {
    if (!auditResult?.xlsx_path) return;
    const endpoint = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    window.open(`${endpoint}/api/au-audit/download-xlsx?xlsx_path=${encodeURIComponent(auditResult.xlsx_path)}`, '_blank');
  };

  const getStatusBadge = (val: string) => {
    if (val === "1" || val === "Yes") return <Badge className="bg-green-500 text-white">Pass</Badge>;
    if (val === "0" || val === "No") return <Badge className="bg-red-500 text-white">Fail</Badge>;
    return <Badge variant="secondary">N/A</Badge>;
  };

  return (
    <div className="h-screen bg-background flex flex-col p-4 relative">
      {processing && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
          <Card className="w-96">
            <CardContent className="pt-6 pb-6 text-center">
              <div className="flex flex-col items-center gap-4">
                <div className="relative h-16 w-16">
                  <div className="absolute inset-0 rounded-full border-4 border-primary/20"></div>
                  <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin"></div>
                </div>
                <h3 className="text-lg font-semibold">Running AU Audit</h3>
                <p className="text-sm text-muted-foreground">Analyzing jobs in {selectedFolder}...</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="max-w-7xl mx-auto w-full flex flex-col h-full">
        <header className="mb-4 flex items-center justify-between shrink-0">
          <h1 className="text-3xl font-semibold tracking-tight">🇦🇺 AU Audit</h1>
          <nav className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => router.push('/')}>← Back</Button>
            <Button variant="outline" size="sm" onClick={() => router.push('/output')}>Output</Button>
          </nav>
        </header>

        <div className="grid grid-cols-3 gap-6 flex-1 overflow-hidden">
          <div className="col-span-1 space-y-4 pr-2">
            <Card>
              <CardHeader><CardTitle>Grouped Folders</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <Button onClick={loadGroupedFolders} variant="outline" size="sm" className="w-full" disabled={loading}>
                  {loading ? 'Loading...' : 'Refresh'}
                </Button>
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                  {folders.map(f => (
                    <div key={f.name} onClick={() => setSelectedFolder(f.name)} className={`p-3 rounded-md cursor-pointer ${selectedFolder === f.name ? 'bg-primary text-primary-foreground' : 'bg-muted/50 hover:bg-muted'}`}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="font-medium text-sm truncate">{f.name}</span>
                        <Badge variant={selectedFolder === f.name ? "secondary" : "outline"}>{f.job_count} jobs</Badge>
                      </div>
                      <div className="flex justify-between text-xs opacity-70">
                        <span>{new Date(f.created).toLocaleDateString()}</span>
                        {f.completed_jobs > 0 && <span className="text-green-500">✓ {f.completed_jobs}/{f.job_count}</span>}
                      </div>
                    </div>
                  ))}
                </div>
                {selectedFolder && (
                  <div className="space-y-2">
                    <Button onClick={() => handleRunAudit(false)} disabled={processing} className="w-full">Run AU Audit</Button>
                    {(folders.find(f => f.name === selectedFolder)?.completed_jobs ?? 0) > 0 && (
                      <Button onClick={() => handleRunAudit(true)} variant="outline" className="w-full border-orange-500 text-orange-600">Resume Remaining</Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {selectedFolder && jobList && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Jobs</CardTitle>
                  <CardDescription>{jobList.completed} done, {jobList.pending} pending</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[calc(100vh-580px)] overflow-y-auto">
                    {jobList.jobs.map(j => (
                      <div key={j.job_id} className={`p-2 rounded-md border text-sm ${j.status === 'completed' ? 'bg-green-50 border-green-200' : 'bg-muted/50'}`}>
                        <div className="flex justify-between items-center">
                          <span className="font-medium truncate">{j.hawb || j.job_id}</span>
                          <Badge variant={j.status === 'completed' ? 'default' : 'secondary'}>{j.status === 'completed' ? '✓' : '⏳'}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Error display */}
            {errorMsg && (
              <Card className="border-red-500">
                <CardContent className="pt-4 pb-4">
                  <p className="text-sm text-red-500">{errorMsg}</p>
                </CardContent>
              </Card>
            )}
          </div>

          <div className="col-span-2 space-y-4 overflow-y-auto pr-2 pb-4">
            {auditResult ? (
              <>
                <Card>
                  <CardHeader>
                    <div className="flex justify-between items-center">
                      <CardTitle>Results</CardTitle>
                      <div className="flex gap-2">
                        <Button onClick={handleDownloadCSV} size="sm" variant="outline">CSV</Button>
                        <Button onClick={handleDownloadXLSX} size="sm">XLSX</Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-8 mb-4">
                      <div><div className="text-2xl font-bold">{auditResult.successful_jobs}</div><div className="text-xs text-muted-foreground">Success</div></div>
                      <div><div className="text-2xl font-bold text-red-500">{auditResult.failed_jobs}</div><div className="text-xs text-muted-foreground">Failed</div></div>
                      <div><div className="text-2xl font-bold">{auditResult.total_jobs}</div><div className="text-xs text-muted-foreground">Total</div></div>
                    </div>
                  </CardContent>
                </Card>

                {auditResult.results.map((r, i) => (
                  <Card key={i}>
                    <CardHeader className="pb-2">
                      <div className="flex justify-between items-center">
                        <CardTitle className="text-base">Job: {r.extraction?.waybill_number || r.job_id}</CardTitle>
                        <Badge variant={r.success ? "default" : "destructive"}>{r.success ? 'Pass' : 'Error'}</Badge>
                      </div>
                      {r.extraction && <CardDescription>Entry: {r.extraction.entry_number} | Month: {r.extraction.audit_month}</CardDescription>}
                    </CardHeader>
                    <CardContent>
                      {r.header_validation && (
                        <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs">
                          {Object.entries(r.header_validation).map(([k, v]) => (
                            !k.endsWith('_reasoning') && (
                              <div key={k} className="flex justify-between items-center py-1 border-b">
                                <span className="capitalize">{k.replace(/_/g, ' ')}</span>
                                {getStatusBadge(v)}
                              </div>
                            )
                          ))}
                        </div>
                      )}
                      {r.auditor_comments && <div className="mt-4 p-2 bg-muted/50 rounded text-xs"><b>Comments:</b> {r.auditor_comments}</div>}
                    </CardContent>
                  </Card>
                ))}
              </>
            ) : !processing && (
              <Card><CardContent className="pt-6 pb-32 text-center text-muted-foreground">Select a folder to see AU audit results</CardContent></Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

